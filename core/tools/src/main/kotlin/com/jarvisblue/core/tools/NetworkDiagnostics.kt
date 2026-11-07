package com.jarvisblue.core.tools

import com.jarvisblue.core.model.NetworkProbe
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.InetAddress
import java.net.Socket
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory

/**
 * Defensive network diagnostics: DNS resolution, TCP reachability and TLS
 * inspection of hosts the user owns or has been authorised to test.
 *
 * The scanner never exploits anything. It observes the handshake the same way a
 * browser does and reports what a defender needs to know: expired certificates,
 * weak negotiation, missing SNI, short chains.
 */
class NetworkDiagnostics {

    /**
     * @param host hostname or IP the user explicitly named.
     * @param port TCP port, defaults to 443.
     */
    suspend fun probe(host: String, port: Int = 443): NetworkProbe = withContext(Dispatchers.IO) {
        val trimmed = host.trim()
        if (trimmed.isEmpty()) {
            return@withContext NetworkProbe(host = host, reachable = false, error = "Empty host")
        }

        val addresses = mutableListOf<String>()
        var dnsMs: Long? = null
        var dnsError: String? = null
        val dnsStart = System.currentTimeMillis()
        try {
            InetAddress.getAllByName(trimmed).forEach { addresses += it.hostAddress ?: it.toString() }
            dnsMs = System.currentTimeMillis() - dnsStart
        } catch (e: Exception) {
            dnsError = e.message ?: "DNS resolution failed"
            dnsMs = System.currentTimeMillis() - dnsStart
        }

        if (addresses.isEmpty()) {
            return@withContext NetworkProbe(
                host = trimmed,
                reachable = false,
                resolvedAddresses = emptyList(),
                dnsMs = dnsMs,
                error = dnsError ?: "Host did not resolve",
            )
        }

        var tcpMs: Long? = null
        var tlsVersion: String? = null
        var tlsCipher: String? = null
        var tlsSubject: String? = null
        var tlsIssuer: String? = null
        var tlsNotAfter: String? = null
        var chainLength: Int? = null
        var error: String? = null

        var socket: Socket? = null
        try {
            val tcpStart = System.currentTimeMillis()
            socket = Socket()
            socket.connect(java.net.InetSocketAddress(trimmed, port), 8000)
            tcpMs = System.currentTimeMillis() - tcpStart

            val factory = SSLContext.getDefault().socketFactory as SSLSocketFactory
            val sslSocket = factory.createSocket(socket, trimmed, port, true) as SSLSocket
            sslSocket.useClientMode = true
            sslSocket.startHandshake()
            val session = sslSocket.session
            tlsVersion = session.protocol
            tlsCipher = session.cipherSuite
            val peer = session.peerCertificates.firstOrNull() as? X509Certificate
            peer?.let {
                tlsSubject = it.subjectDN?.name
                tlsIssuer = it.issuerDN?.name
                tlsNotAfter = it.notAfter.toString()
                chainLength = session.peerCertificates.size
            }
            sslSocket.close()
        } catch (e: SSLHandshakeException) {
            error = "TLS handshake failed: ${e.message}"
        } catch (e: CertificateException) {
            error = "Certificate rejected: ${e.message}"
        } catch (e: Exception) {
            error = e.message ?: "Connection failed"
        } finally {
            runCatching { socket?.close() }
        }

        NetworkProbe(
            host = trimmed,
            reachable = tcpMs != null,
            resolvedAddresses = addresses,
            dnsMs = dnsMs,
            tcpPort = port,
            tcpConnectMs = tcpMs,
            tlsVersion = tlsVersion,
            tlsCipher = tlsCipher,
            tlsSubject = tlsSubject,
            tlsIssuer = tlsIssuer,
            tlsNotAfter = tlsNotAfter,
            certificateChainLength = chainLength,
            error = error,
        )
    }

    /**
     * Checks whether the device's TLS trust store would accept the host's chain.
     * A host that fails here is very likely to fail for the user's other apps too.
     */
    suspend fun trustCheck(host: String, port: Int = 443): TrustResult = withContext(Dispatchers.IO) {
        var socket: Socket? = null
        return@withContext try {
            socket = Socket()
            socket.connect(java.net.InetSocketAddress(host.trim(), port), 8000)
            val sslSocket = SSLContext.getDefault().socketFactory
                .createSocket(socket, host.trim(), port, true) as SSLSocket
            sslSocket.startHandshake()
            val trusted = runCatching {
                sslSocket.session.peerCertificates.firstOrNull() as? X509Certificate ?: error("no certificate")
            }.isSuccess
            sslSocket.close()
            TrustResult(trusted = trusted, detail = "Chain presented and accepted by the system trust store")
        } catch (e: Exception) {
            TrustResult(trusted = false, detail = e.message ?: "Trust validation failed")
        } finally {
            runCatching { socket?.close() }
        }
    }

    data class TrustResult(val trusted: Boolean, val detail: String)
}
