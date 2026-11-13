package com.jarvisblue.feature.studio

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.model.GateType
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.SectionHeader
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueBright
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent

@Composable
fun QuantumLabScreen(
    state: QuantumLabUiState,
    onPreset: (String) -> Unit,
    onSimulate: () -> Unit,
    onAddGate: (GateType, Int) -> Unit,
    onRemoveGate: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        NoticeBanner(
            "A phone has no quantum processor. Everything here is a classical state-vector " +
                "simulation running on the CPU, shown so gate behaviour can be studied and " +
                "compared against a classical baseline. No quantum speed-up is claimed.",
            accent = AmberWarn,
        )

        GlowCard(title = "Circuit", subtitle = state.circuit.name, accent = BlueCore) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf("bell" to "Bell pair", "ghz" to "GHZ-3", "qft2" to "2-qubit QFT")
                        .forEach { (key, label) ->
                            FilterChip(
                                selected = state.circuit.id == key,
                                onClick = { onPreset(key) },
                                label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                            )
                        }
                }

                CircuitDiagram(
                    qubitCount = state.circuit.qubits,
                    gates = state.circuit.gates.map { it.type },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height((state.circuit.qubits * 46 + 40).dp),
                )

                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.availableGates.forEach { gate ->
                        OutlinedButton(
                            onClick = { onAddGate(gate, 0) },
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                                horizontal = 10.dp,
                                vertical = 6.dp,
                            ),
                        ) {
                            Text(gate.name, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    OutlinedButton(onClick = onRemoveGate) {
                        Text("Undo", style = MaterialTheme.typography.labelSmall)
                    }
                }

                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf(256, 1024, 4096).forEach { shots ->
                        FilterChip(
                            selected = state.shots == shots,
                            onClick = { onPreset(state.circuit.id) },
                            label = { Text("$shots shots", style = MaterialTheme.typography.labelSmall) },
                        )
                    }
                    Button(onClick = onSimulate, enabled = !state.isBusy) {
                        Text(if (state.isBusy) "Simulating…" else "Simulate")
                    }
                }

                Text(
                    text = "Shots: ${state.shots} · Gates: ${state.circuit.gates.size}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        state.result?.let { result ->
            GlowCard(title = "Measurement", subtitle = "${result.shots} shots · ${result.elapsedMs} ms", accent = CyanAccent) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    result.outcomes.forEach { outcome ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                text = outcome.bitstring,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Medium,
                            )
                            Text(
                                text = "${"%.3f".format(outcome.probability)}  (${outcome.count})",
                                style = MaterialTheme.typography.bodyMedium,
                                color = BlueBright,
                            )
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = result.note,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        SectionHeader(
            title = "Transparent performance",
            subtitle = "Simulator time versus a classical baseline for the same circuit",
        )
        state.result?.let { result ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusPill(text = "Simulator ${result.elapsedMs} ms", color = BlueCore)
                StatusPill(text = "Baseline ${result.classicalBaselineMs ?: 0} ms", color = CyanAccent)
                StatusPill(text = "State vector ${result.stateVectorSize}", color = BlueCore)
            }
        }
    }
}

/**
 * Draws the circuit as wires and gates. This is a schematic, not a real
 * quantum diagram, and it is labelled as such in the lab copy.
 */
@Composable
private fun CircuitDiagram(
    qubitCount: Int,
    gates: List<GateType>,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) {
        val laneHeight = 46f
        val top = 20f
        val wireStart = 30f
        val wireEnd = size.width - 30f

        repeat(qubitCount) { qubit ->
            val y = top + qubit * laneHeight
            drawLine(
                color = BlueCore.copy(alpha = 0.55f),
                start = Offset(wireStart, y),
                end = Offset(wireEnd, y),
                strokeWidth = 2f,
            )
            drawCircle(color = CyanAccent.copy(alpha = 0.8f), radius = 4f, center = Offset(wireStart - 12f, y))
        }

        val columnWidth = if (gates.isEmpty()) 0f else (wireEnd - wireStart - 40f) / gates.size.coerceAtLeast(1)
        gates.forEachIndexed { index, gate ->
            val x = wireStart + 20f + columnWidth * index + columnWidth / 2f
            val target = (index % qubitCount)
            val y = top + target * laneHeight
            when (gate) {
                GateType.CNOT, GateType.CZ -> {
                    drawCircle(color = Color.White, radius = 6f, center = Offset(x, y))
                    drawCircle(color = BlueBright, radius = 4f, center = Offset(x, y), style = Stroke(2f))
                    if (qubitCount > 1) {
                        drawLine(
                            color = BlueCore.copy(alpha = 0.6f),
                            start = Offset(x, y),
                            end = Offset(x, top + (target + 1) * laneHeight),
                            strokeWidth = 2f,
                        )
                        drawCircle(
                            color = BlueBright,
                            radius = 7f,
                            center = Offset(x, top + (target + 1) * laneHeight),
                            style = Stroke(2f),
                        )
                    }
                }
                GateType.SWAP -> {
                    drawCircle(color = BlueBright, radius = 5f, center = Offset(x, y))
                }
                else -> {
                    drawRoundRect(
                        color = BlueBright.copy(alpha = 0.18f),
                        topLeft = Offset(x - 16f, y - 14f),
                        size = androidx.compose.ui.geometry.Size(32f, 28f),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(6f, 6f),
                    )
                    drawRoundRect(
                        color = BlueBright,
                        topLeft = Offset(x - 16f, y - 14f),
                        size = androidx.compose.ui.geometry.Size(32f, 28f),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(6f, 6f),
                        style = Stroke(1.5f),
                    )
                }
            }
        }
    }
}
