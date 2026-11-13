package com.jarvisblue.mobile.services

import com.jarvisblue.core.database.PeerRepository
import com.jarvisblue.core.model.BridgeJob
import com.jarvisblue.core.model.BridgeJobKind
import com.jarvisblue.core.model.BridgeRequest
import com.jarvisblue.core.model.PcState
import com.jarvisblue.core.model.PcStatus
import com.jarvisblue.core.security.SecretVault
import com.jarvisblue.core.windows.BridgeClient
import javax.inject.Inject
import javax.inject.Singleton

/**
 * App-level gateway to the JARVIS BLUE Windows desktop.
 *
 * It resolves the paired peer from the encrypted database, derives the base URL
 * and delegates the signed calls to [BridgeClient]. The shared secret is read
 * from the Keystore-backed vault for every request and never cached in a field.
 */
@Singleton
class WindowsBridgeGateway @Inject constructor(
    private val bridgeClient: BridgeClient,
    private val peerRepository: PeerRepository,
    private val secretVault: SecretVault,
) {

    private suspend fun peer() = peerRepository.trusted()

    private fun baseUrl(host: String, port: Int): String? =
        runCatching { BridgeEndpoint.baseUrl(host, port) }.getOrNull()

    suspend fun status(): PcStatus {
        val peer = peer() ?: return PcStatus(
            peerId = "windows",
            state = PcState.PAIRING_REQUIRED,
            detail = "No Windows machine is paired",
        )
        val endpoint = baseUrl(peer.host, peer.port) ?: return PcStatus(
            peerId = peer.peerId,
            state = PcState.DEGRADED,
            detail = "Invalid bridge endpoint: HTTPS is required",
        )
        return bridgeClient.status(endpoint).valueOrNull
            ?: PcStatus(
                peerId = peer.peerId,
                state = PcState.OFFLINE,
                hostname = peer.displayName,
                detail = "The Windows bridge did not respond",
            )
    }

    suspend fun jobs(): List<BridgeJob> {
        val peer = peer() ?: return emptyList()
        val endpoint = baseUrl(peer.host, peer.port) ?: return emptyList()
        return bridgeClient.jobs(endpoint).valueOrNull ?: emptyList()
    }

    suspend fun submit(request: BridgeRequest): BridgeJob {
        val peer = peer() ?: return BridgeJob(
            id = "unpaired",
            kind = request.kind,
            title = request.title,
            state = com.jarvisblue.core.model.BridgeJobState.REJECTED,
            error = "No Windows machine is paired",
        )
        val endpoint = baseUrl(peer.host, peer.port) ?: return BridgeJob(
            id = "invalid-bridge-endpoint",
            kind = request.kind,
            title = request.title,
            state = com.jarvisblue.core.model.BridgeJobState.REJECTED,
            error = "Invalid bridge endpoint: HTTPS is required",
        )
        return bridgeClient.submitJob(endpoint, request).valueOrNull
            ?: BridgeJob(
                id = "failed",
                kind = request.kind,
                title = request.title,
                state = com.jarvisblue.core.model.BridgeJobState.FAILED,
                error = "The Windows bridge did not accept the job",
            )
    }

    suspend fun cancel(jobId: String): Boolean {
        val peer = peer() ?: return false
        val endpoint = baseUrl(peer.host, peer.port) ?: return false
        return bridgeClient.cancelJob(endpoint, jobId).valueOrNull ?: false
    }
}
