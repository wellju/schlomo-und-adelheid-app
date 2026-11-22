import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/source-serif-4/600.css';
import './styles/tokens.css';
import { mount } from 'svelte';
import App from './App.svelte';

// last colour scheme of this device until the engine has answered (EGM B15); only a display preference
let darstellung = 'system';
try { darstellung = localStorage.getItem('darstellung') ?? 'system'; } catch { /* blocked storage: system */ }
document.documentElement.dataset.theme = ['system', 'hell', 'dunkel'].includes(darstellung) ? darstellung : 'system';
mount(App, { target: document.getElementById('app')! });
