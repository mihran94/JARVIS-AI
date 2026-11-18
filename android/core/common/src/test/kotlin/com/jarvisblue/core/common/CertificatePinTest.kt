package com.jarvisblue.core.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

class CertificatePinTest {

    /** A fingerprint that is the SHA-256 of a made-up certificate. */
    private val fingerprint = "a".repeat(64)

    @Test
    fun `a fingerprint is sixty-four hexadecimal characters`() {
        assertTrue(CertificatePin.isFingerprint(fingerprint))
        assertTrue(CertificatePin.isFingerprint(fingerprint.uppercase()))
        assertTrue(CertificatePin.isFingerprint("  $fingerprint  "))
        assertFalse(CertificatePin.isFingerprint(""))
        assertFalse(CertificatePin.isFingerprint(null))
        assertFalse(CertificatePin.isFingerprint("a".repeat(63)))
        assertFalse(CertificatePin.isFingerprint("a".repeat(65)))
        assertFalse(CertificatePin.isFingerprint("z".repeat(64)))
    }

    @Test
    fun `the pin is the same digest in base64`() {
        // sha256 of the byte 0xaa, repeated.
        val digest = ByteArray(32) { 0xaa.toByte() }
        val expected = "sha256/" + java.util.Base64.getEncoder().encodeToString(digest)
        assertEquals(expected, CertificatePin.pinOf("aa".repeat(32)))
    }

    @Test
    fun `a damaged fingerprint is refused rather than repaired`() {
        var refused = false
        try {
            CertificatePin.pinOf("not a fingerprint")
        } catch (error: IllegalArgumentException) {
            refused = true
        }
        assertTrue("a damaged fingerprint must be refused", refused)
    }

    @Test
    fun `the fingerprint is read out of the pairing code`() {
        val code = """
            JARVIS-BRIDGE-v1
            bridge=https://pc.example.lan:8765
            key=jarvis-iphone-v1
            secret=shared-secret
            expires=1764000000
            fp=$fingerprint
        """.trimIndent()
        assertEquals(fingerprint, CertificatePin.fingerprintFromPairingCode(code))
    }

    @Test
    fun `a code without a fingerprint has none`() {
        val code = """
            JARVIS-BRIDGE-v1
            bridge=https://pc.example.lan:8765
            key=jarvis-iphone-v1
            secret=shared-secret
            expires=1764000000
        """.trimIndent()
        assertNull(CertificatePin.fingerprintFromPairingCode(code))
        assertNull(CertificatePin.fingerprintFromPairingCode(null))
        assertNull(CertificatePin.fingerprintFromPairingCode(""))
    }

    @Test
    fun `a damaged fingerprint in a code is not used`() {
        val code = "JARVIS-BRIDGE-v1\nfp=not-a-fingerprint"
        assertNull(CertificatePin.fingerprintFromPairingCode(code))
    }

    @Test
    fun `the trust manager accepts the pinned certificate and refuses another`() {
        // A certificate is made from a real DER form so the digest is real.
        val pinned = CertificateFixture.certificate
        val pinnedFingerprint = CertificateFixture.fingerprintOf(pinned)
        val manager = CertificatePin.trustManagerFor(pinnedFingerprint)

        manager.checkServerTrusted(arrayOf(pinned), "RSA")

        val other = CertificateFixture.otherCertificate
        var refused = false
        try {
            manager.checkServerTrusted(arrayOf(other), "RSA")
        } catch (error: CertificateException) {
            refused = true
        }
        assertTrue("a certificate that is not the pinned one must be refused", refused)
    }

    @Test
    fun `the trust manager refuses a chain with no certificate`() {
        val manager = CertificatePin.trustManagerFor(fingerprint)
        var refused = false
        try {
            manager.checkServerTrusted(emptyArray(), "RSA")
        } catch (error: CertificateException) {
            refused = true
        }
        assertTrue(refused)
    }

    @Test
    fun `the trust manager never asks for a client certificate`() {
        val manager = CertificatePin.trustManagerFor(fingerprint)
        var refused = false
        try {
            manager.checkClientTrusted(arrayOf(CertificateFixture.certificate), "RSA")
        } catch (error: CertificateException) {
            refused = true
        }
        assertTrue(refused)
    }

    @Test
    fun `the tls context is built for the pinned certificate`() {
        val context = CertificatePin.sslContextFor(fingerprint)
        assertNotNull(context)
        assertEquals("TLS", context.protocol)
    }

    @Test
    fun `the host name is not what decides`() {
        // The identity of the peer is the pinned certificate. The host name
        // the owner typed is not what proves anything, so it is not checked,
        // and the trust manager is what refuses a wrong certificate.
        assertTrue(CertificatePin.hostnameVerifier().verify("pc.example.lan", null))
    }
}

/**
 * A real certificate, read from a real PEM file, so the fingerprints and
 * the digests in these tests are the ones the code really computes.
 */
internal object CertificateFixture {

    private fun read(name: String): X509Certificate {
        val stream = CertificateFixture::class.java.getResourceAsStream(name)
            ?: throw IllegalStateException("The test certificate $name is missing.")
        return stream.use {
            CertificateFactory.getInstance("X.509").generateCertificate(it) as X509Certificate
        }
    }

    /** The certificate the phone is told to pin. */
    val certificate: X509Certificate by lazy { read("/bridge-cert.pem") }

    /** A different, perfectly valid certificate that must be refused. */
    val otherCertificate: X509Certificate by lazy { read("/other-cert.pem") }

    fun fingerprintOf(certificate: X509Certificate): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(certificate.encoded)
        return digest.joinToString("") { "%02x".format(it) }
    }
}
