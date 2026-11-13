package com.jarvisblue.core.tools

import com.jarvisblue.core.model.Gate
import com.jarvisblue.core.model.GateType
import com.jarvisblue.core.model.QuantumCircuit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class QuantumSimulatorTest {

    private val simulator = QuantumSimulator()

    @Test
    fun `bell pair yields only 00 and 11`() {
        val result = simulator.simulate(QuantumSimulator.bellPair())
        val bitstrings = result.outcomes.map { it.bitstring }.toSet()
        assertEquals(setOf("00", "11"), bitstrings)
    }

    @Test
    fun `bell pair probabilities are balanced`() {
        val result = simulator.simulate(QuantumSimulator.bellPair())
        val top = result.outcomes.sortedByDescending { it.probability }
        assertTrue(top[0].probability > 0.45)
        assertTrue(top[1].probability > 0.45)
        assertEquals(2, top.size)
    }

    @Test
    fun `single hadamard produces a uniform superposition`() {
        val circuit = QuantumCircuit(
            id = "h1",
            name = "H",
            qubits = 1,
            gates = listOf(Gate(GateType.H, target = 0)),
            shots = 100,
        )
        val result = simulator.simulate(circuit)
        assertEquals(2, result.outcomes.size)
        assertTrue(result.outcomes.all { it.probability > 0.45 })
    }

    @Test
    fun `x gate flips the basis state deterministically`() {
        val circuit = QuantumCircuit(
            id = "x1",
            name = "X",
            qubits = 1,
            gates = listOf(Gate(GateType.X, target = 0)),
            shots = 100,
        )
        val result = simulator.simulate(circuit)
        assertEquals("1", result.outcomes.first().bitstring)
        assertTrue(result.outcomes.first().probability > 0.99)
    }

    @Test
    fun `simulator refuses more qubits than it supports`() {
        val circuit = QuantumCircuit(
            id = "big",
            name = "Too big",
            qubits = 20,
            gates = emptyList(),
        )
        val error = runCatching { simulator.simulate(circuit) }.exceptionOrNull()
        assertTrue(error is IllegalArgumentException)
    }
}
