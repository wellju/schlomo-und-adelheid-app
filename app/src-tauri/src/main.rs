// Hide the console window of the release build on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    schlomo_app::run()
}
