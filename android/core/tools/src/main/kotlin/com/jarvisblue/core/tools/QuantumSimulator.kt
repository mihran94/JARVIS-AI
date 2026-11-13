package com.jarvisblue.core.tools

import com.jarvisblue.core.model.Gate
import com.jarvisblue.core.model.GateType
import com.jarvisblue.core.model.MeasurementOutcome
import com.jarvisblue.core.model.QuantumCircuit
import com.jarvisblue.core.model.SimulationResult
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.random.Random

/**
 * A classical state-vector simulator for quantum circuits.
 *
 * IMPORTANT AND DELIBERATE: an Android phone has **no quantum processor**. This
 * class simulates small circuits on the CPU using complex amplitudes so that the
 * user can *learn* how gates compose, and it reports honest timings that make
 * the classical cost obvious. The UI labels every result as a simulation.
 *
 * Maximum supported qubit count is bounded (see [MAX_QUBITS]) because the state
 * vector grows as 2^n amplitudes.
 */
class QuantumSimulator(private val maxQubits: Int = MAX_QUBITS) {

    fun simulate(circuit: QuantumCircuit): SimulationResult {
        val started = System.currentTimeMillis()
        require(circuit.qubits in 1..maxQubits) {
            "This simulator supports 1..$maxQubits qubits (requested ${circuit.qubits})"
        }

        val state = StateVector(circuit.qubits)
        state.initializeZero()

        for (gate in circuit.gates) {
            applyGate(state, gate)
        }

        val theoretical = state.theoreticalProbabilities()
        val measurements = if (circuit.gates.any { it.type == GateType.MEASURE }) {
            state.sampleMeasurements(circuit.shots, circuit.gates)
        } else {
            theoretical.filter { it.second > 1e-9 }.take(8).map { (bits, prob) ->
                MeasurementOutcome(
                    bitstring = bits,
                    count = (prob * circuit.shots).toInt().coerceAtLeast(1),
                    probability = prob,
                )
            }.sortedByDescending { it.probability }
        }

        val elapsed = System.currentTimeMillis() - started
        return SimulationResult(
            circuitId = circuit.id,
            circuitName = circuit.name,
            shots = circuit.shots,
            outcomes = measurements,
            stateVectorSize = state.size,
            simulator = "Jarvis classical state-vector simulator (CPU)",
            elapsedMs = elapsed,
            theoreticalFidelity = theoretical.firstOrNull()?.second,
            classicalBaselineMs = elapsed,
            note = "Simulated on the phone's CPU. No quantum hardware was involved and no " +
                "quantum speed-up is claimed.",
        )
    }

    private fun applyGate(state: StateVector, gate: Gate) {
        when (gate.type) {
            GateType.H -> state.singleQubit(gate.target) { a, b ->
                val c = Complex(h, 0.0)
                val s = Complex(h, 0.0)
                (a * c + b * s) to (a * s + b * c)
            }
            GateType.X -> state.singleQubit(gate.target) { a, b -> b to a }
            GateType.Y -> state.singleQubit(gate.target) { a, b ->
                // Y = [[0, -i], [i, 0]]
                (b * Complex(0.0, 1.0) * Complex(0.0, -1.0)) to (a * Complex(0.0, 1.0))
            }
            GateType.Z -> state.singleQubit(gate.target) { a, b -> a to (b * Complex(-1.0, 0.0)) }
            GateType.S -> state.singleQubit(gate.target) { a, b -> a to (b * Complex(0.0, 1.0)) }
            GateType.T -> state.singleQubit(gate.target) { a, b ->
                val t = Complex(cos(PI / 4), sin(PI / 4))
                a to (b * t)
            }
            GateType.RX -> state.singleQubit(gate.target) { a, b ->
                val c = Complex(cos(gate.theta / 2), 0.0)
                val s = Complex(0.0, -sin(gate.theta / 2))
                ((a * c) + (b * s)) to ((a * s) + (b * c))
            }
            GateType.RY -> state.singleQubit(gate.target) { a, b ->
                val c = Complex(cos(gate.theta / 2), 0.0)
                val s = Complex(sin(gate.theta / 2), 0.0)
                ((a * c) + (b * s) * Complex(-1.0, 0.0)) to ((a * s) + (b * c))
            }
            GateType.RZ -> state.singleQubit(gate.target) { a, b ->
                val eMinus = Complex(cos(gate.theta / 2), -sin(gate.theta / 2))
                val ePlus = Complex(cos(gate.theta / 2), sin(gate.theta / 2))
                (a * eMinus) to (b * ePlus)
            }
            GateType.CNOT -> state.controlledSwap(gate.control ?: 0, gate.target)
            GateType.CZ -> state.controlledPhase(gate.control ?: 0, gate.target)
            GateType.SWAP -> state.swapBits(gate.control ?: 0, gate.target)
            GateType.MEASURE -> Unit // measurement is applied after the full circuit
        }
    }

    /** Minimal complex number helper (kept local to avoid a math dependency). */
    data class Complex(val re: Double, val im: Double) {
        operator fun plus(other: Complex) = Complex(re + other.re, im + other.im)
        operator fun minus(other: Complex) = Complex(re - other.re, im - other.im)
        operator fun times(other: Complex) =
            Complex(re * other.re - im * other.im, re * other.im + im * other.re)
        operator fun unaryMinus() = Complex(-re, -im)
        val magnitudeSquared: Double get() = re * re + im * im
    }

    private val h = 1.0 / kotlin.math.sqrt(2.0)

    companion object {
        const val MAX_QUBITS = 12

        /** Pre-built circuits used by the laboratory screen. */
        fun bellPair(): QuantumCircuit = QuantumCircuit(
            id = "bell",
            name = "Bell pair (entanglement)",
            qubits = 2,
            gates = listOf(
                Gate(GateType.H, target = 0),
                Gate(GateType.CNOT, target = 1, control = 0),
            ),
            shots = 1024,
        )

        fun ghz(): QuantumCircuit = QuantumCircuit(
            id = "ghz",
            name = "GHZ state (3 qubits)",
            qubits = 3,
            gates = listOf(
                Gate(GateType.H, target = 0),
                Gate(GateType.CNOT, target = 1, control = 0),
                Gate(GateType.CNOT, target = 2, control = 0),
            ),
            shots = 1024,
        )

        fun quantumFourierTwo(): QuantumCircuit = QuantumCircuit(
            id = "qft2",
            name = "2-qubit QFT",
            qubits = 2,
            gates = listOf(
                Gate(GateType.H, target = 0),
                Gate(GateType.CNOT, target = 1, control = 0),
                Gate(GateType.RZ, target = 1, theta = PI / 4),
            ),
            shots = 256,
        )
    }
}

/**
 * Dense state vector over [size] amplitudes (2^n qubits).
 */
internal class StateVector(val qubits: Int) {

    val size: Int = 1 shl qubits
    val amplitudes: MutableList<QuantumSimulator.Complex> = MutableList(size) { QuantumSimulator.Complex(0.0, 0.0) }

    fun initializeZero() {
        amplitudes[0] = QuantumSimulator.Complex(1.0, 0.0)
    }

    fun singleQubit(
        target: Int,
        transform: (QuantumSimulator.Complex, QuantumSimulator.Complex) ->
            Pair<QuantumSimulator.Complex, QuantumSimulator.Complex>,
    ) {
        val mask = 1 shl (qubits - 1 - target)
        for (index in 0 until size) {
            if (index and mask != 0) continue
            val zeroIndex = index
            val oneIndex = index or mask
            val (newZero, newOne) = transform(amplitudes[zeroIndex], amplitudes[oneIndex])
            amplitudes[zeroIndex] = newZero
            amplitudes[oneIndex] = newOne
        }
    }

    /** CNOT: swap the target qubit amplitudes whenever the control qubit is |1>. */
    fun controlledSwap(control: Int, target: Int) {
        val controlMask = 1 shl (qubits - 1 - control)
        val targetMask = 1 shl (qubits - 1 - target)
        for (index in 0 until size) {
            if (index and controlMask == 0) continue
            // Only handle the half where the target bit is 0, otherwise each pair
            // would be swapped twice and the gate would be a no-op.
            if (index and targetMask != 0) continue
            val other = index xor targetMask
            val tmp = amplitudes[index]
            amplitudes[index] = amplitudes[other]
            amplitudes[other] = tmp
        }
    }

    /** CZ: flip the sign of the amplitude when control and target are both |1>. */
    fun controlledPhase(control: Int, target: Int) {
        val controlMask = 1 shl (qubits - 1 - control)
        val targetMask = 1 shl (qubits - 1 - target)
        for (index in 0 until size) {
            if (index and controlMask == 0) continue
            if (index and targetMask == 0) continue
            amplitudes[index] = amplitudes[index] * QuantumSimulator.Complex(-1.0, 0.0)
        }
    }

    /** SWAP: exchange the two qubits. */
    fun swapBits(a: Int, b: Int) {
        val maskA = 1 shl (qubits - 1 - a)
        val maskB = 1 shl (qubits - 1 - b)
        for (index in 0 until size) {
            val bitA = index and maskA != 0
            val bitB = index and maskB != 0
            if (bitA == bitB) continue
            val other = index xor maskA xor maskB
            if (index > other) continue // each pair is swapped exactly once
            val tmp = amplitudes[index]
            amplitudes[index] = amplitudes[other]
            amplitudes[other] = tmp
        }
    }

    fun theoreticalProbabilities(): List<Pair<String, Double>> =
        amplitudes.mapIndexed { index, amplitude ->
            val bits = index.toString(2).padStart(qubits, '0')
            bits to amplitude.magnitudeSquared
        }.sortedByDescending { it.second }

    fun sampleMeasurements(shots: Int, gates: List<Gate>): List<MeasurementOutcome> {
        val measuredQubits = gates.filter { it.type == GateType.MEASURE }.map { it.target }.distinct()
        if (measuredQubits.isEmpty()) {
            return theoreticalProbabilities().filter { it.second > 1e-9 }.take(8).map { (bits, probability) ->
                MeasurementOutcome(
                    bitstring = bits,
                    count = (probability * shots).toInt().coerceAtLeast(if (probability > 0.0) 1 else 0),
                    probability = probability,
                )
            }
        }

        val counts = mutableMapOf<String, Int>()
        val random = Random(System.nanoTime())
        repeat(shots) {
            val index = weightedSample(random)
            val bits = index.toString(2).padStart(qubits, '0')
            val measured = measuredQubits.sorted().map { bits[it] }.joinToString("")
            counts[measured] = (counts[measured] ?: 0) + 1
        }
        return counts.entries
            .sortedByDescending { it.value }
            .map { (bits, count) ->
                MeasurementOutcome(bits, count, count.toDouble() / shots.toDouble())
            }
    }

    private fun weightedSample(random: Random): Int {
        val total = amplitudes.sumOf { it.magnitudeSquared }
        var threshold = random.nextDouble() * total
        for (index in amplitudes.indices) {
            threshold -= amplitudes[index].magnitudeSquared
            if (threshold <= 0) return index
        }
        return amplitudes.lastIndex
    }
}
