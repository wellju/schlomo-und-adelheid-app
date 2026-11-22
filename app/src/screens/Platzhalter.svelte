<script lang="ts">
  // Fallback for an unknown address.
  import AppShell from '../lib/components/AppShell.svelte';
  let { teile }: { teile: string[] } = $props();
</script>

<AppShell aktiv={teile[0]} anonStatus={{ stufe: 'uebersicht', gesperrt: 0 }} bereich="Navigation" titel="Nicht gefunden">
  <div class="empty"><h2 class="h2" style="color:var(--tx)">Seite nicht gefunden</h2><div>Diese Adresse gibt es in der App nicht.</div><a class="btn p" href="#/faelle">Zu den Fällen</a></div>
</AppShell>
