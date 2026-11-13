package com.jarvisblue.core.tools

import com.jarvisblue.core.model.FindingSeverity
import org.junit.Assert.assertTrue
import org.junit.Test

class SecurityScannerTest {

    private val scanner = SecurityScanner()

    @Test
    fun `flags cleartext http endpoints`() {
        val result = scanner.scanText("val endpoint = \"http://api.example.com/v1/data\"")
        assertTrue(result.findings.any { it.title.contains("Cleartext") })
    }

    @Test
    fun `flags disabled certificate validation as critical`() {
        val result = scanner.scanText(
            """
            class TrustAll {
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            }
            """.trimIndent(),
        )
        val finding = result.findings.firstOrNull { it.title.contains("Certificate") }
        assertTrue(finding != null)
        assertTrue(finding!!.severity == FindingSeverity.CRITICAL)
    }

    @Test
    fun `flags hardcoded api keys`() {
        val result = scanner.scanText("""val apiKey = "sk-9f8a7b6c5d4e3f2a1b0c9d8e"""")
        assertTrue(result.findings.any { it.title.contains("hard-coded") })
    }

    @Test
    fun `flags world readable files`() {
        val result = scanner.scanText("val f = File(path, MODE_WORLD_READABLE)")
        assertTrue(result.findings.any { it.title.contains("World-readable") })
    }

    @Test
    fun `clean code produces no findings`() {
        val result = scanner.scanText(
            """
            fun add(a: Int, b: Int): Int {
                return a + b
            }
            """.trimIndent(),
        )
        assertTrue(result.findings.isEmpty())
    }
}
