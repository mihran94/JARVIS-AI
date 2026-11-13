package com.jarvisblue.feature.studio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.model.AuthorizationGrant
import com.jarvisblue.core.model.AuthorizationKind
import com.jarvisblue.core.model.NetworkProbe
import com.jarvisblue.core.model.SecurityFinding
import com.jarvisblue.core.tools.NetworkDiagnostics
import com.jarvisblue.core.tools.SecurityScanner
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

data class CyberLabUiState(
    val host: String = "",
    val port: String = "443",
    val authorization: AuthorizationGrant? = null,
    val probe: NetworkProbe? = null,
    val trustDetail: String = "",
    val reviewTarget: String = "",
    val findings: List<SecurityFinding> = emptyList(),
    val isBusy: Boolean = false,
    val statusLine: String = "Awaiting authorisation",
    val error: String? = null,
)

@HiltViewModel
class CyberLabViewModel @Inject constructor(
    private val network: NetworkDiagnostics,
    private val scanner: SecurityScanner,
) : ViewModel() {

    private val _state = MutableStateFlow(CyberLabUiState())
    val state: StateFlow<CyberLabUiState> = _state.asStateFlow()

    fun setHost(host: String) {
        _state.value = _state.value.copy(host = host)
    }

    fun setPort(port: String) {
        _state.value = _state.value.copy(port = port.filter { it.isDigit() })
    }

    fun setReviewTarget(text: String) {
        _state.value = _state.value.copy(reviewTarget = text)
    }

    /**
     * Records the user's ownership/authorisation statement. Active probing is
     * blocked until this exists, which keeps the module strictly defensive.
     */
    fun grantAuthorization(kind: AuthorizationKind, scope: String, notes: String) {
        val grant = AuthorizationGrant(
            id = UUID.randomUUID().toString(),
            kind = kind,
            scope = scope,
            grantedAtEpochMs = System.currentTimeMillis(),
            notes = notes,
        )
        _state.value = _state.value.copy(
            authorization = grant,
            statusLine = "Authorised for ${grant.scope}",
        )
    }

    fun revokeAuthorization() {
        _state.value = _state.value.copy(
            authorization = null,
            probe = null,
            statusLine = "Authorisation revoked",
        )
    }

    fun probeHost() {
        val current = _state.value
        if (current.authorization == null) {
            _state.value = current.copy(error = "Record ownership or written authorisation first.")
            return
        }
        if (current.host.isBlank()) {
            _state.value = current.copy(error = "Enter a host to inspect.")
            return
        }
        val port = current.port.toIntOrNull() ?: 443
        _state.value = current.copy(isBusy = true, statusLine = "Inspecting ${current.host}…", error = null)
        viewModelScope.launch {
            try {
                val probe = network.probe(current.host, port)
                val trust = network.trustCheck(current.host, port)
                _state.value = _state.value.copy(
                    probe = probe,
                    trustDetail = if (trust.trusted) {
                        "Certificate chain is accepted by the device trust store."
                    } else {
                        "Trust check failed: ${trust.detail}"
                    },
                    isBusy = false,
                    statusLine = "Inspection finished",
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    isBusy = false,
                    statusLine = "Failed",
                    error = t.message ?: "The inspection could not be completed",
                )
            }
        }
    }

    fun reviewText() {
        val text = _state.value.reviewTarget
        if (text.isBlank()) return
        val result = scanner.scanText(text, "submission.txt")
        _state.value = _state.value.copy(
            findings = result.findings,
            statusLine = "Review finished — ${result.findings.size} finding(s)",
        )
    }
}
