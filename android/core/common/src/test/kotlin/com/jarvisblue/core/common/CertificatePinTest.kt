package com.jarvisblue.core.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.security.MessageDigest
import java.util.Base64
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

    private fun read(encoded: String): X509Certificate {
        val bytes = Base64.getDecoder().decode(encoded)
        return CertificateFactory.getInstance("X.509")
            .generateCertificate(ByteArrayInputStream(bytes)) as X509Certificate
    }

    /**
     * The certificate the phone is told to pin.
     *
     * The two certificates are written into this file and not kept as
     * files next to it: the Android tree does not keep `.pem` files in
     * the repository, so a test that read one from there would have
     * nothing to read on a fresh checkout.
     */
    val certificate: X509Certificate by lazy { read(BRIDGE_CERTIFICATE) }

    /** A different, perfectly valid certificate that must be refused. */
    val otherCertificate: X509Certificate by lazy { read(OTHER_CERTIFICATE) }

    private const val BRIDGE_CERTIFICATE =
        """MIIDPzCCAiegAwIBAgIUfh2KYDgYaaddw+QtwYu1Bt3eUQ8wDQYJKoZIhvcNAQELBQAwLzEZMBcGA1UEAwwQSkFSVklTIEFJIGJyaWRnZTESMBAGA1UECgwJSkFSVklTIEFJMB4XDTI2MTExODIwNTkxMVoXDTM2MTExNTIwNTkxMVowLzEZMBcGA1UEAwwQSkFSVklTIEFJIGJyaWRnZTESMBAGA1UECgwJSkFSVklTIEFJMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv1mkdD1CBZfm9Rcz/1V99DOW78emZldgI4AhFliKDp8ACk1wn4vwbV8nHbEnrDwtvZVr3oy7Y/2/kJwKW/hC4KrSu0bOnxEI+JfD0V3ryTfZN2D9i6C2Oacsnm0nimiusuU3w1i0D36wi0CWYLIdgaaxag6lu3kEHef3UY+70Ce4ZbU1iiLBlRkOAauXlU8T7hNmDMU6R6uEJgJN7ySNH4jzU9mbuJmbVXFZC/Yc9fk9tacBsr82DIWG9MvmZ18418Cwn8AR9T3AztpVqBblEpu2AoLT81S8DeD885Me1rJw0xooZJmh4JEcsY9uy17UOqmoePT8kLM6wBopyCss0QIDAQABo1MwUTAdBgNVHQ4EFgQUliSIM7gADUfzyR6EfMAJY6Kt/wYwHwYDVR0jBBgwFoAUliSIM7gADUfzyR6EfMAJY6Kt/wYwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEALcKgf+qIbFe5Mx5imSjHUVBDsIhdlQ9BGAml4s6g8BSs71InxRp874qdjPvE1fzsVsYUnDWZWZ+UtyZBWYOKAJcgVC3V42mqbIuI5hajX1DjPdcJKYYmQrl71Vlki+MYr2m/F4ue+9ffELXOtU5DIQehhEPDeYzhNSY3ryGeTYSYNGal3J7LVqU2igRRndSvkonO/ttIFZKJfvhjx37vUqh7Vjyhylunjyf+XTLEbxdNa5L3Id87xqUWgQKmQ6Udl+nWc0Gs4s/xfaiyL0ZpdrUjdasSNzND/0nYHZYDR50UsTKViCum6G3/WS/YaJ+qTpgT/KeccQ/ZIdjgcbs2Sg=="""

    private const val OTHER_CERTIFICATE =
        """MIIDLzCCAhegAwIBAgIUeN55AvSekOAFetF2ig7qToKFRi4wDQYJKoZIhvcNAQELBQAwJzEVMBMGA1UEAwwMU29tZW9uZSBFbHNlMQ4wDAYDVQQKDAVPdGhlcjAeFw0yNjExMTgyMDU5MTJaFw0zNjExMTUyMDU5MTJaMCcxFTATBgNVBAMMDFNvbWVvbmUgRWxzZTEOMAwGA1UECgwFT3RoZXIwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCwASXUf7EoRx3mVm8kVgW9r8uvePub9NcYLY4hcfv2AIIq2BPdK+89pxLETE3q7+lOgLpE2PnaAuf0bcLB4kV+kgy+Q2znFnWBMLrpjWiVs1dKEmxV9UYVgVitBWunjvN2veQaSM1Cm/jAtsHHN/9tZZ/bNyPKZPFQMr6or4rET/azdmLfCEx5toYF+KalMFHimm4NnT+0gjYb5Gg+CtnrjgPvZUnYJcJIxcanhkQMlUw5wA9A64kiU3cJ8AJuF6VqXO/POmEX9n7DFaoskhOr/4bBOM1dmgqIExP2Hr7VLDC0TQKUXaSH5V10XXamoQxsmZXnkYSJFbrE65tk9xg/AgMBAAGjUzBRMB0GA1UdDgQWBBSFfG3SnzWI14iWjKyRItdzkoWDljAfBgNVHSMEGDAWgBSFfG3SnzWI14iWjKyRItdzkoWDljAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQCO56H3JzpSX/45ra2DHYJNwuiijfXZcvjjl2mfZA7wzXLAS+qD2W6r+/gMDs788/gMAgQr9B2BdVEAqJL/nvJdLF4R7x0IVkmPxMqq8GmU7bKPjspz5efXQn3tABtEYbkdDr82N4LUr9QvoVgS14fYgP0PalRRrqec/mt5Ez5un2c0QLKE9A7OZbS1QWyLpHSxw3pADaAy4uC9Yc79RrFMt/D/N5ood9Cv59UGUJ4fkjyc3lTolSyfXIoKVSSwbHJnzpyhjJD7BeGgjpLyv8UaYZKqBIE0TfL8hfE8HoWfeO2y8tXM/ZrItA2/0KMWPhK3xQGhKv8FTMUr6RRpaU5S"""

    fun fingerprintOf(certificate: X509Certificate): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(certificate.encoded)
        return digest.joinToString("") { "%02x".format(it) }
    }
}
