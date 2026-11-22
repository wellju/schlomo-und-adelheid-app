// File paths come only from the system dialog (Tauri). In development there is no dialog: the screen shows a path
// field instead (synthetic test files only). A path is used for one call and never stored (docs/ui-api.md).
import { istEntwicklung } from './engine/client';

export const pfadFeld = () => import.meta.env.DEV && istEntwicklung(); // never in a production build (EGM B16)

export async function oeffnen(name: string, endungen: string[]): Promise<string | null> {
  const { open } = await import('@tauri-apps/plugin-dialog');
  const r = await open({ multiple: false, directory: false, filters: [{ name, extensions: endungen }] });
  return typeof r === 'string' ? r : null;
}

export async function speichern(name: string, endung: string, vorschlag: string): Promise<string | null> {
  const { save } = await import('@tauri-apps/plugin-dialog');
  return await save({ defaultPath: vorschlag, filters: [{ name, extensions: [endung] }] });
}

export async function ordnerWaehlen(): Promise<string | null> {
  const { open } = await import('@tauri-apps/plugin-dialog');
  const r = await open({ multiple: false, directory: true });
  return typeof r === 'string' ? r : null;
}
