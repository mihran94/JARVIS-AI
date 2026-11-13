package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

/**
 * Quantum research types. These model *classical simulation* of quantum circuits.
 * An Android handset has no quantum processor; every measurement here comes from a
 * state-vector simulator running on the CPU, and the UI labels it as such.
 */
@Serializable
enum class GateType {
    H, X, Y, Z, S, T, RX, RY, RZ, CNOT, CZ, SWAP, MEASURE,
}

@Serializable
data class Gate(
    val type: GateType,
    val target: Int,
    val control: Int? = null,
    val theta: Double = 0.0,
    val label: String = "",
)

@Serializable
data class QuantumCircuit(
    val id: String,
    val name: String,
    val qubits: Int,
    val gates: List<Gate>,
    val shots: Int = 1024,
)

@Serializable
data class MeasurementOutcome(
    val bitstring: String,
    val count: Int,
    val probability: Double,
)

@Serializable
data class SimulationResult(
    val circuitId: String,
    val circuitName: String,
    val shots: Int,
    val outcomes: List<MeasurementOutcome>,
    val stateVectorSize: Int,
    val simulator: String,
    val elapsedMs: Long,
    val theoreticalFidelity: Double? = null,
    val classicalBaselineMs: Long? = null,
    val note: String = "",
)
