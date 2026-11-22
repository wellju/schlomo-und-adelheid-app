<script lang="ts">
  // Label is mandatory: a status is never colour alone (Übergabe-Board).
  let { tone, label, icon = '' }: { tone: 'ok' | 'wn' | 'er' | 'na' | 'ai' | 'svp'; label: string; icon?: string } = $props();
</script>

<span class="pl {tone}">{#if icon}<span aria-hidden="true">{icon}</span>{/if}{label}</span>
