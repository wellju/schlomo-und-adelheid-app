//! Tauri shell (ADR 0001: Rust only for starting the engine and the file dialogs). Relays the JSON-lines channel of
//! `engine ui` (docs/ui-api.md) unchanged: one line from the window to stdin, every stdout line as event `engine-line`.
//! The engine lives in the resource folder (`engine/`, PyInstaller --onedir), so `externalBin` is not used.
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

#[derive(Default)]
struct Engine {
    inner: Mutex<Option<(Child, ChildStdin)>>,
    // Each start gets a new number; only the current engine may report its end (EGM B11, C10).
    generation: Arc<AtomicU64>,
}

fn engine_path(app: &AppHandle) -> tauri::Result<PathBuf> {
    // Development override, only in debug builds: a release build always starts the bundled engine.
    #[cfg(debug_assertions)]
    if let Ok(p) = std::env::var("SCHLOMO_ENGINE") {
        return Ok(PathBuf::from(p));
    }
    let exe = if cfg!(windows) { "engine/engine.exe" } else { "engine/engine" };
    app.path().resolve(exe, BaseDirectory::Resource)
}

/// The engine's stderr holds only log lines without content (docs/ui-api.md); they go to engine.log in the app's log
/// folder, which the guide names for support (EGM B6). Without a log folder they are dropped.
fn log_target(app: &AppHandle) -> Stdio {
    app.path()
        .app_log_dir()
        .ok()
        .and_then(|dir| std::fs::create_dir_all(&dir).ok().map(|_| dir.join("engine.log")))
        .and_then(|file| OpenOptions::new().create(true).append(true).open(file).ok())
        .map(Stdio::from)
        .unwrap_or_else(Stdio::null)
}

fn spawn(app: &AppHandle, generation: &Arc<AtomicU64>) -> Result<(Child, ChildStdin), String> {
    let path = engine_path(app).map_err(|_| "E_INTERN".to_string())?;
    let mut cmd = Command::new(&path);
    cmd.arg("ui").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(log_target(app));
    // Bundled Tesseract (Windows build): the engine finds it through SCHLOMO_TESSERACT (external.find).
    let tess = if cfg!(windows) { "tesseract/tesseract.exe" } else { "tesseract/tesseract" };
    if let Ok(exe) = app.path().resolve(tess, BaseDirectory::Resource) {
        if exe.is_file() {
            cmd.env("SCHLOMO_TESSERACT", &exe);
            if let Some(dir) = exe.parent() {
                cmd.env("TESSDATA_PREFIX", dir.join("tessdata"));
            }
        }
    }
    if let Some(dir) = path.parent() {
        cmd.current_dir(dir); // never the data folder or one of its parents (store.data_dir)
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    let mut child = cmd.spawn().map_err(|_| "E_INTERN".to_string())?;
    let stdin = child.stdin.take().ok_or("E_INTERN")?;
    let stdout = child.stdout.take().ok_or("E_INTERN")?;
    let handle = app.clone();
    let mine = generation.fetch_add(1, Ordering::SeqCst) + 1;
    let current = Arc::clone(generation);
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(l) if !l.trim().is_empty() => {
                    let _ = handle.emit("engine-line", l);
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
        // stdout closed: this engine has ended. Only if no newer one runs, open calls fail in the window and the
        // next call starts it again; a late end of an old engine never aborts calls of the new one.
        if current.load(Ordering::SeqCst) == mine {
            let _ = handle.emit("engine-line", r#"{"id":"engine-ende"}"#);
        }
    });
    Ok((child, stdin))
}

/// Async, so it runs off the main thread: a large line while the engine is busy never blocks the window (EGM C8).
#[tauri::command]
async fn engine_send(app: AppHandle, state: State<'_, Engine>, line: String) -> Result<(), String> {
    if line.contains('\n') {
        return Err("E_SCHEMA".into());
    }
    let mut guard = state.inner.lock().map_err(|_| "E_INTERN")?;
    let running = matches!(guard.as_mut().map(|(c, _)| c.try_wait()), Some(Ok(None)));
    if !running {
        *guard = Some(spawn(&app, &state.generation)?);
    }
    let (_, stdin) = guard.as_mut().unwrap();
    stdin.write_all(line.as_bytes()).and_then(|_| stdin.write_all(b"\n")).and_then(|_| stdin.flush())
        .map_err(|_| "E_INTERN".to_string())
}

fn stop(state: &Engine) {
    state.generation.fetch_add(1, Ordering::SeqCst); // the end is ours, nobody needs to hear it
    if let Ok(mut guard) = state.inner.lock() {
        if let Some((mut child, stdin)) = guard.take() {
            drop(stdin); // EOF: the engine leaves its loop and clears the plain text in memory (ram.clear)
            let deadline = Instant::now() + Duration::from_secs(3);
            while Instant::now() < deadline {
                if let Ok(Some(_)) = child.try_wait() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            let _ = child.kill();
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Engine::default())
        .invoke_handler(tauri::generate_handler![engine_send])
        .build(tauri::generate_context!())
        .expect("tauri app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop(&app.state::<Engine>());
            }
        });
}
