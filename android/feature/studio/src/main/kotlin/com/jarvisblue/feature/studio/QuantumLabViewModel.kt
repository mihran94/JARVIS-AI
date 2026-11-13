package com.jarvisblue.feature.studio

import androidx.lifecycle.ViewModel
import com.jarvisblue.core.model.Gate
import com.jarvisblue.core.model.GateType
import com.jarvisblue.core.model.QuantumCircuit
import com.jarvisblue.core.model.SimulationResult
import com.jarvisblue.core.tools.QuantumSimulator
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID
import javax.inject.Inject

data class QuantumLabUiState(
    val circuit: QuantumCircuit = QuantumSimulator.bellPair(),
    val result: SimulationResult? = null,
    val shots: Int = 1024,
    val isBusy: Boolean = false,
    val statusLine: String = "Ready",
    val error: String? = null,
    val availableGates: List<GateType> = listOf(
        GateType.H, GateType.X, GateType.Y, GateType.Z,
        GateType.S, GateType.T, GateType.RX, GateType.RY, GateType.RZ,
        GateType.CNOT, GateType.CZ, GateType.SWAP,
    ),
)

@HiltViewModel
class QuantumLabViewModel @Inject constructor(
    private val simulator: QuantumSimulator,
) : ViewModel() {

    private val _state = MutableStateFlow(QuantumLabUiState())
    val state: StateFlow<QuantumLabUiState> = _state.asStateFlow()

    fun loadPreset(name: String) {
        val circuit = when (name) {
            "ghz" -> QuantumSimulator.ghz()
            "qft2" -> QuantumSimulator.quantumFourierTwo()
            else -> QuantumSimulator.bellPair()
        }
        _state.value = _state.value.copy(circuit = circuit, result = null, statusLine = "Loaded $name")
    }

    fun setShots(shots: Int) {
        _state.value = _state.value.copy(shots = shots.coerceIn(16, 8192))
    }

    fun addGate(type: GateType, target: Int) {
        val circuit = _state.value.circuit
        val gate = when (type) {
            GateType.CNOT, GateType.CZ, GateType.SWAP -> Gate(
                type = type,
                target = target.coerceIn(1, circuit.qubits - 1),
                control = 0,
            )
            else -> Gate(type = type, target = target.coerceIn(0, circuit.qubits - 1))
        }
        _state.value = _state.value.copy(
            circuit = circuit.copy(gates = circuit.gates + gate),
            result = null,
            statusLine = "Added ${type.name}",
        )
    }

    fun removeLastGate() {
        val circuit = _state.value.circuit
        _state.value = _state.value.copy(
            circuit = circuit.copy(gates = circuit.gates.dropLast(1)),
            result = null,
            statusLine = "Removed last gate",
        )
    }

    fun simulate() {
        val circuit = _state.value.circuit
        _state.value = _state.value.copy(isBusy = true, statusLine = "Simulating…", error = null)
        try {
            val result = simulator.simulate(circuit.copy(shots = _state.value.shots))
            _state.value = _state.value.copy(
                result = result,
                isBusy = false,
                statusLine = "Simulated in ${result.elapsedMs} ms",
            )
        } catch (t: Throwable) {
            _state.value = _state.value.copy(
                isBusy = false,
                statusLine = "Failed",
                error = t.message ?: "The simulation failed",
            )
        }
    }

    fun newCircuit(qubits: Int) {
        val safe = qubits.coerceIn(1, QuantumSimulator.MAX_QUBITS)
        _state.value = _state.value.copy(
            circuit = QuantumCircuit(
                id = UUID.randomUUID().toString(),
                name = "Custom circuit",
                qubits = safe,
                gates = emptyList(),
                shots = _state.value.shots,
            ),
            result = null,
            statusLine = "New $safe-qubit circuit",
        )
    }
}
