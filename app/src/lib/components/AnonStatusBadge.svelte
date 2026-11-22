<script lang="ts">
  import type { AnonStatus } from '../anon';
  let { status, live = true }: { status: AnonStatus; live?: boolean } = $props();
  const view = $derived.by(() => {
    switch (status.stufe) {
      case 'nicht_geprueft': return { ton: 'na', text: '○ Anonymisierung: nicht geprüft' };
      case 'offen': return { ton: 'wn', text: `! Anonymisierung: ${status.anzahl} ${status.anzahl === 1 ? 'Dokument' : 'Dokumente'} offen` };
      case 'unsicher': return { ton: 'er', text: '✕ Anonymisierung unsicher · Weitergabe gesperrt' };
      case 'bestaetigt': return { ton: 'ok', text: '✓ Schwärzung bestätigt' };
      case 'uebersicht': return status.gesperrt
        ? { ton: 'er', text: `✕ Anonymisierung: ${status.gesperrt} ${status.gesperrt === 1 ? 'Fall' : 'Fälle'} gesperrt` }
        : { ton: 'ok', text: '✓ Anonymisierung: kein Fall gesperrt' };
      case 'kein_fall': return { ton: 'na', text: '○ Keine importierten Dokumente' };
    }
  });
</script>

<span class="pl {view.ton}" role={live ? 'status' : undefined} data-testid={live ? 'anon-status' : undefined}>{view.text}</span>
