package com.jarvisblue.feature.command

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.database.PeerRepository
import com.jarvisblue.core.model.BridgeJob
import com.jarvisblue.core.model.BridgeJobKind
import com.jarvisblue.core.model.BridgeRequest
import com.jarvisblue.core.model.PcState
import com.jarvisblue.core.model.PcStatus
import com.jarvisblue.core.model.WindowsPeer
import com.jarvisblue.core.security.SecretVault
import com.jarvisblue.core.windows.BridgeClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

data class WindowsUiState(
    val peer: WindowsPeer? = null,
    val hostInput: String = "",
    val portInput: String = "8765",
    val secretInput: String = "",
    val status: PcStatus? = null,
    val jobs: List<BridgeJob> = emptyList(),
    val isBusy: Boolean = false,
    val statusLine: String = "Not paired",
    val error: String? = null,
    val lastEvent: String? = null,
)

@HiltViewModel
class WindowsViewModel @Inject constructor(
    private val bridgeClient: BridgeClient,
    private val secretVault: SecretVault,
    private val peerRepository: PeerRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(WindowsUiState())
    val state: StateFlow<WindowsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            peerRepository.observeAll().collect { peers ->
                _state.value = _state.value.copy(peer = peers.firstOrNull())
            }
        }
    }

    fun setHost(host: String) {
        _state.value = _state.value.copy(hostInput = host)
    }

    fun setPort(port: String) {
        _state.value = _state.value.copy(portInput = port.filter { it.isDigit() })
    }

    fun setSecret(secret: String) {
        _state.value = _state.value.copy(secretInput = secret)
    }

    /** Stores the shared secret in the Keystore-backed vault and remembers the peer. */
    fun pair() {
        val host = _state.value.hostInput.trim()
        val port = _state.value.portInput.toIntOrNull() ?: 8765
        val secret = _state.value.secretInput.trim()
        if (host.isEmpty() || secret.length < 32) {
            _state.value = _state.value.copy(
                error = "Enter the Windows address and its 32+ character pairing secret")
            return
        }
        if (runCatching { DesktopEndpoint.baseUrl(host, port) }.isFailure) {
            _state.value = _state.value.copy(
                error = "Use the HTTPS address and port shown in Windows JARVIS")
            return
        }
        viewModelScope.launch {
            try {
                secretVault.put(SecretVault.ALIAS_WINDOWS_PEER, secret)
                val peer = WindowsPeer(
                    peerId = "windows-${host.lowercase()}",
                    displayName = "Windows JARVIS",
                    host = host,
                    port = port,
                    pairedAtEpochMs = System.currentTimeMillis(),
                    lastSeenEpochMs = 0L,
                    sharedSecretAlias = SecretVault.ALIAS_WINDOWS_PEER,
                    trusted = true,
                )
                peerRepository.save(peer)
                _state.value = _state.value.copy(
                    peer = peer,
                    secretInput = "",
                    statusLine = "PC details saved; checking secure connection...",
                    error = null,
                )
                refresh()
            } catch (_: Exception) {
                _state.value = _state.value.copy(
                    secretInput = "",
                    error = "Could not save the pairing details on this phone.")
            }
        }
    }

    fun unpair() {
        viewModelScope.launch {
            secretVault.remove(SecretVault.ALIAS_WINDOWS_PEER)
            _state.value.peer?.let { peerRepository.delete(it.peerId) }
            _state.value = _state.value.copy(
                peer = null,
                status = null,
                jobs = emptyList(),
                statusLine = "Unpaired — the pairing secret was deleted",
            )
        }
    }

    fun refresh() {
        val peer = _state.value.peer ?: run {
            _state.value = _state.value.copy(statusLine = "Pair with a Windows machine first")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(isBusy = true)
            val base = baseUrl(peer)
            if (base == null) {
                _state.value = _state.value.copy(
                    isBusy = false,
                    error = "Invalid Windows address. HTTPS is required.",
                    statusLine = "Windows link unavailable",
                )
                return@launch
            }
            val statusResult = bridgeClient.status(base)
            val jobsResult = bridgeClient.jobs(base)
            _state.value = _state.value.copy(
                status = statusResult.valueOrNull,
                jobs = jobsResult.valueOrNull ?: _state.value.jobs,
                isBusy = false,
                statusLine = statusResult.errorOrNull?.message ?: "Status updated",
                error = statusResult.errorOrNull?.message,
            )
        }
    }

    fun submitJob(title: String, kind: BridgeJobKind) {
        val peer = _state.value.peer ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(isBusy = true)
            val base = baseUrl(peer)
            if (base == null) {
                _state.value = _state.value.copy(
                    isBusy = false, error = "HTTPS Windows bridge is required")
                return@launch
            }
            val result = bridgeClient.submitJob(
                base,
                BridgeRequest(kind = kind, title = title, payloadJson = "{}", requireApproval = true),
            )
            _state.value = _state.value.copy(
                isBusy = false,
                statusLine = result.errorOrNull?.message ?: "Job submitted",
                error = result.errorOrNull?.message,
            )
            refresh()
        }
    }

    fun cancelJob(jobId: String) {
        val peer = _state.value.peer ?: return
        viewModelScope.launch {
            val base = baseUrl(peer) ?: return@launch
            val result = bridgeClient.cancelJob(base, jobId)
            _state.value = _state.value.copy(
                statusLine = result.errorOrNull?.message
                    ?: if (result.valueOrNull == true) "Job cancelled" else "Cancellation was refused",
            )
            refresh()
        }
    }

    /** Polls the bridge so the dashboard reflects the desktop in near real time. */
    fun startPolling(intervalSeconds: Long = 5) {
        viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(intervalSeconds * 1000)
            }
        }
    }

    private fun baseUrl(peer: WindowsPeer): String? =
        runCatching { DesktopEndpoint.baseUrl(peer.host, peer.port) }.getOrNull()
}
