<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import * as d3 from 'd3'
import { apiGet } from '../services/api'

const props = defineProps({
  players: { type: Array, required: true },
  selectedPlayerId: { type: String, default: '' },
  selectedPlayerName: { type: String, default: '' },
  selectedComparisonPlayerId: { type: String, default: '' },
  selectedComparisonPlayerName: { type: String, default: '' },
  activeStoryStep: { type: String, default: 'overview' },
  clusterRequestId: { type: String, default: '' },
  embedded: { type: Boolean, default: false }
})

const emit = defineEmits([
  'update:selectedPlayerId',
  'update:selectedComparisonPlayerId',
  'update:activeStoryStep',
  'select-match-context'
])

const selectedPlayer = computed({
  get: () => props.selectedPlayerId,
  set: (value) => emit('update:selectedPlayerId', value)
})

const selectedComparisonPlayer = computed({
  get: () => props.selectedComparisonPlayerId,
  set: (value) => emit('update:selectedComparisonPlayerId', value)
})

const primarySvgRef = ref()
const comparisonSvgRef = ref()
const dualCompareSvgRef = ref()
const error = ref('')

const primaryDataset = ref([])
const comparisonDataset = ref([])

const selectedMatchKey = ref('')

const matchKeyForRow = (row) => {
  const hasRowId = row?.row_id !== null && row?.row_id !== undefined && row.row_id !== ''
  if (hasRowId) return `row:${row.row_id}`
  if (row?.match_id != null && row.match_id !== '') return `match:${row.match_id}`
  return `composite:${row?.player_id ?? ''}|${row?.opponent_id ?? ''}|${row?.match_date ?? ''}`
}

const selectedPlayerRows = computed(() =>
  props.players
    .filter((row) => row.player_id === selectedPlayer.value)
    .map((row) => ({
      ...row,
      matchDateObj: row.match_date ? new Date(row.match_date) : null
    }))
    .sort((a, b) => d3.descending(a.matchDateObj, b.matchDateObj))
)

const matchOptions = computed(() =>
  selectedPlayerRows.value.map((row) => ({
    key: matchKeyForRow(row),
    label: `${row.match_date ?? '-'} · vs ${row.opponent_name ?? row.opponent_id ?? '-'} · ${row.surface ?? '-'} · match_id=${row.match_id ?? '-'}`
  }))
)

const selectedMatchRow = computed(() =>
  selectedPlayerRows.value.find((row) => matchKeyForRow(row) === selectedMatchKey.value) ?? null
)

const normalizeToPercent = (value) => {
  const numeric = Number(value ?? 0)
  if (!Number.isFinite(numeric)) return 0
  return numeric <= 1 ? numeric * 100 : numeric
}

const playerOptions = computed(() =>
  props.players.map((p) => ({
    player_id: p.player_id,
    player_name: p.player_name ?? p.player_id
  }))
)

const selectedPlayerLabel = computed(() => {
  if (props.selectedPlayerName && String(props.selectedPlayerName).trim()) return props.selectedPlayerName
  if (!selectedPlayer.value) return 'No player selected'
  const selectedOption = playerOptions.value.find((option) => option.player_id === selectedPlayer.value)
  return selectedOption?.player_name ?? selectedPlayer.value
})

const selectedComparisonPlayerLabel = computed(() => {
  if (props.selectedComparisonPlayerName && String(props.selectedComparisonPlayerName).trim()) return props.selectedComparisonPlayerName
  if (!selectedComparisonPlayer.value) return 'No comparison player selected'
  const selectedOption = playerOptions.value.find((option) => option.player_id === selectedComparisonPlayer.value)
  return selectedOption?.player_name ?? selectedComparisonPlayer.value
})

onMounted(async () => {
  if (!selectedPlayer.value && playerOptions.value.length > 0) {
    selectedPlayer.value = playerOptions.value[0].player_id
  }
  if (!selectedComparisonPlayer.value && playerOptions.value.length > 1) {
    const fallback = playerOptions.value.find((option) => option.player_id !== selectedPlayer.value)
    selectedComparisonPlayer.value = fallback?.player_id ?? ''
  }
  await loadSeries()
})

watch(
  playerOptions,
  (options) => {
    if (!options.length) return
    const optionIds = options.map((option) => option.player_id)
    if (!optionIds.includes(selectedPlayer.value)) {
      selectedPlayer.value = options[0].player_id
    }
    if (selectedComparisonPlayer.value && !optionIds.includes(selectedComparisonPlayer.value)) {
      selectedComparisonPlayer.value = ''
    }
    if (!selectedComparisonPlayer.value && optionIds.length > 1) {
      selectedComparisonPlayer.value = optionIds.find((id) => id !== selectedPlayer.value) ?? ''
    }
  },
  { immediate: true }
)

watch(matchOptions, (options) => {
  if (!options.length) {
    selectedMatchKey.value = ''
    return
  }
  if (!options.some((option) => option.key === selectedMatchKey.value)) {
    selectedMatchKey.value = options[0].key
  }
}, { immediate: true })

watch([selectedPlayer, selectedComparisonPlayer], async ([primary, secondary]) => {
  if (primary && primary === secondary) {
    selectedComparisonPlayer.value = ''
    return
  }
  await loadSeries()
})

watch([primaryDataset, comparisonDataset], async () => {
  await nextTick()
  drawCharts()
}, { deep: true })

async function fetchSeriesForPlayer(playerId) {
  if (!playerId) return []
  const [elo, ace, win] = await Promise.all([
    apiGet(`/players/${encodeURIComponent(playerId)}/metrics/timeseries`, { metric: 'elo', limit: 20000 }),
    apiGet(`/players/${encodeURIComponent(playerId)}/metrics/timeseries`, { metric: 'ace_pct', limit: 20000 }),
    apiGet(`/players/${encodeURIComponent(playerId)}/metrics/timeseries`, { metric: 'win_pct', limit: 20000 })
  ])

  const map = new Map()
  for (const point of elo.points) {
    map.set(point.match_date, { date: new Date(point.match_date), elo: Number(point.value ?? 0), ace: null, win: null })
  }
  for (const point of ace.points) {
    const rec = map.get(point.match_date) ?? { date: new Date(point.match_date), elo: null, ace: null, win: null }
    rec.ace = normalizeToPercent(point.value)
    map.set(point.match_date, rec)
  }
  for (const point of win.points) {
    const rec = map.get(point.match_date) ?? { date: new Date(point.match_date), elo: null, ace: null, win: null }
    rec.win = normalizeToPercent(point.value)
    map.set(point.match_date, rec)
  }

  return [...map.values()].sort((a, b) => d3.ascending(a.date, b.date))
}

async function loadSeries() {
  error.value = ''
  try {
    const [primary, secondary] = await Promise.all([
      fetchSeriesForPlayer(selectedPlayer.value),
      fetchSeriesForPlayer(selectedComparisonPlayer.value)
    ])
    primaryDataset.value = primary
    comparisonDataset.value = secondary
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    primaryDataset.value = []
    comparisonDataset.value = []
  }
}

function continueToMatchExplanation() {
  if (!selectedPlayer.value || !selectedMatchRow.value) return
  emit('select-match-context', {
    player_id: selectedPlayer.value,
    match_key: matchKeyForRow(selectedMatchRow.value)
  })
}

function drawSinglePlayerChart(svgElement, dataset, title, accentColor) {
  const svg = d3.select(svgElement)
  svg.selectAll('*').remove()
  if (!dataset.length) return

  const width = 940
  const height = 300
  const margin = { top: 28, right: 34, bottom: 42, left: 56 }
  svg.attr('viewBox', `0 0 ${width} ${height}`)

  const x = d3.scaleTime().domain(d3.extent(dataset, (d) => d.date)).range([margin.left, width - margin.right])
  const yLeft = d3.scaleLinear().domain(d3.extent(dataset, (d) => d.elo)).nice().range([height - margin.bottom, margin.top])
  const yRight = d3.scaleLinear().domain([0, 100]).range([height - margin.bottom, margin.top])

  svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`).call(d3.axisBottom(x))
  svg.append('g').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(yLeft))
  svg.append('g').attr('transform', `translate(${width - margin.right},0)`).call(d3.axisRight(yRight))

  const line = (key, scale) =>
    d3
      .line()
      .defined((d) => d[key] !== null)
      .x((d) => x(d.date))
      .y((d) => scale(d[key]))

  svg.append('path').datum(dataset).attr('fill', 'none').attr('stroke', accentColor).attr('stroke-width', 2.25).attr('d', line('elo', yLeft))
  svg.append('path').datum(dataset).attr('fill', 'none').attr('stroke', '#059669').attr('stroke-width', 1.8).attr('d', line('win', yRight))
  svg.append('path').datum(dataset).attr('fill', 'none').attr('stroke', '#f97316').attr('stroke-width', 1.8).attr('d', line('ace', yRight))

  svg.append('text').attr('x', margin.left).attr('y', margin.top - 10).attr('fill', accentColor).attr('font-weight', 600).text(title)
}

function drawComparisonChart() {
  const svg = d3.select(dualCompareSvgRef.value)
  svg.selectAll('*').remove()

  if (!primaryDataset.value.length || !comparisonDataset.value.length) return

  const combined = [...primaryDataset.value, ...comparisonDataset.value]
  const width = 940
  const height = 300
  const margin = { top: 24, right: 30, bottom: 42, left: 56 }
  svg.attr('viewBox', `0 0 ${width} ${height}`)

  const x = d3.scaleTime().domain(d3.extent(combined, (d) => d.date)).range([margin.left, width - margin.right])
  const y = d3.scaleLinear().domain(d3.extent(combined, (d) => d.elo)).nice().range([height - margin.bottom, margin.top])

  svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`).call(d3.axisBottom(x))
  svg.append('g').attr('transform', `translate(${margin.left},0)`).call(d3.axisLeft(y))

  const eloLine = d3
    .line()
    .defined((d) => d.elo !== null)
    .x((d) => x(d.date))
    .y((d) => y(d.elo))

  svg.append('path').datum(primaryDataset.value).attr('fill', 'none').attr('stroke', '#1d4ed8').attr('stroke-width', 2.2).attr('d', eloLine)
  svg.append('path').datum(comparisonDataset.value).attr('fill', 'none').attr('stroke', '#7c3aed').attr('stroke-width', 2.2).attr('d', eloLine)

  const legend = [
    { label: `${selectedPlayerLabel.value} (Elo)`, color: '#1d4ed8' },
    { label: `${selectedComparisonPlayerLabel.value} (Elo)`, color: '#7c3aed' }
  ]

  const legendGroup = svg.append('g').attr('transform', `translate(${margin.left}, ${height - margin.bottom + 30})`)
  const entries = legendGroup.selectAll('g').data(legend).enter().append('g').attr('transform', (_, i) => `translate(${i * 260},0)`)
  entries.append('line').attr('x1', 0).attr('x2', 24).attr('y1', 0).attr('y2', 0).attr('stroke-width', 3).attr('stroke', (d) => d.color)
  entries.append('text').attr('x', 32).attr('y', 4).attr('font-size', 11).text((d) => d.label)

  svg.append('text').attr('x', margin.left).attr('y', margin.top - 8).text('Elo comparison over time')
}

function drawCharts() {
  if (primarySvgRef.value) {
    drawSinglePlayerChart(primarySvgRef.value, primaryDataset.value, `${selectedPlayerLabel.value} — performance`, '#1d4ed8')
  }
  if (comparisonSvgRef.value) {
    drawSinglePlayerChart(comparisonSvgRef.value, comparisonDataset.value, `${selectedComparisonPlayerLabel.value} — performance`, '#7c3aed')
  }
  if (dualCompareSvgRef.value) {
    drawComparisonChart()
  }
}
</script>

<template>
  <section class="panel">
    <h2 v-if="!embedded">Player performance (multi-metric time series)</h2>

    <div class="trend-header">
      <h3>Trend context for {{ selectedPlayerLabel }} vs {{ selectedComparisonPlayerLabel }}</h3>
      <button
        v-if="selectedMatchRow && selectedMatchKey"
        type="button"
        class="secondary"
        @click="continueToMatchExplanation"
      >
        View predicted outcomes &amp; explanation →
      </button>
    </div>

    <div class="filters">
      <label>
        Player A
        <select v-model="selectedPlayer">
          <option v-for="player in playerOptions" :key="player.player_id" :value="player.player_id">
            {{ player.player_name }}
          </option>
        </select>
      </label>

      <label>
        Player B
        <select v-model="selectedComparisonPlayer">
          <option value="">No comparison player</option>
          <option
            v-for="player in playerOptions"
            :key="`comparison-${player.player_id}`"
            :value="player.player_id"
            :disabled="player.player_id === selectedPlayer"
          >
            {{ player.player_name }}
          </option>
        </select>
      </label>

      <label>
        Match in context (Player A)
        <select v-model="selectedMatchKey" :disabled="!matchOptions.length">
          <option v-for="option in matchOptions" :key="option.key" :value="option.key">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <svg ref="primarySvgRef" class="chart"></svg>
    <svg ref="comparisonSvgRef" class="chart"></svg>
    <h3>Elo comparison over time</h3>
    <svg ref="dualCompareSvgRef" class="chart"></svg>
  </section>
</template>
