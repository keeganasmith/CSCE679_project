<script setup>
import { computed } from 'vue'

const props = defineProps({
  activeStoryStep: { type: String, default: 'overview' },
  activeTab: { type: String, default: 'overview' },
  overviewContext: {
    type: Object,
    default: () => ({
      clusterLabel: 'All clusters',
      summary: 'Generate groups to inspect archetypes.'
    })
  },
  performanceContext: {
    type: Object,
    default: () => ({
      playerName: 'No player selected',
      trendHints: 'Choose a player to inspect timeline behavior.'
    })
  },
  explainerContext: {
    type: Object,
    default: () => ({
      matchLabel: 'No match selected',
      winProbability: null
    })
  }
})

const emit = defineEmits(['update:activeStoryStep', 'update:activeTab'])

const steps = [
  {
    key: 'overview',
    title: 'Step 1',
    subtitle: 'Segment player archetypes (Cluster Overview)'
  },
  {
    key: 'performance',
    title: 'Step 2',
    subtitle: 'Validate trend behavior (Player Performance)'
  },
  {
    key: 'tree',
    title: 'Step 3',
    subtitle: 'Explain a concrete match prediction (Decision-tree Explainer)'
  }
]

const currentStep = computed(() => props.activeStoryStep || props.activeTab || 'overview')

const helperText = computed(() => {
  if (currentStep.value === 'overview') {
    return `${props.overviewContext.clusterLabel}: ${props.overviewContext.summary}`
  }

  if (currentStep.value === 'performance') {
    return `${props.performanceContext.playerName}: ${props.performanceContext.trendHints}`
  }

  const winProb = Number(props.explainerContext.winProbability)
  const probLabel = Number.isFinite(winProb)
    ? `${(winProb * 100).toFixed(1)}% win probability`
    : 'win probability pending'
  return `${props.explainerContext.matchLabel}: ${probLabel}`
})

function activateStep(stepKey) {
  emit('update:activeStoryStep', stepKey)
  emit('update:activeTab', stepKey)
}
</script>

<template>
  <section class="panel story-stepper">
    <div class="stepper-row">
      <button
        v-for="step in steps"
        :key="step.key"
        type="button"
        class="step-chip"
        :class="{ active: currentStep === step.key }"
        @click="activateStep(step.key)"
      >
        <span class="step-title">{{ step.title }}</span>
        <span class="step-subtitle">{{ step.subtitle }}</span>
      </button>
    </div>
    <p class="subtle helper-text">{{ helperText }}</p>
  </section>
</template>

<style scoped>
.story-stepper {
  padding: 12px 16px;
}

.stepper-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.step-chip {
  border: 1px solid #30363d;
  border-radius: 8px;
  background: #0d1117;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  text-align: left;
  transition: border-color 0.12s, background 0.12s;
}

.step-chip:hover {
  border-color: #6e7681;
  background: #21262d;
}

.step-chip.active {
  border-color: #2f81f7;
  background: #1f4f8f;
}

.step-title {
  font-size: 11px;
  font-weight: 600;
  color: #8b949e;
  letter-spacing: 0.04em;
}

.step-chip.active .step-title {
  color: #2f81f7;
}

.step-subtitle {
  font-size: 12px;
  line-height: 1.3;
  color: #6e7681;
}

.step-chip.active .step-subtitle {
  color: #8b949e;
}

.helper-text {
  margin: 10px 0 0;
  font-size: 12px;
  color: #6e7681;
}
</style>
