package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

@Serializable
data class DeviceDiagnostics(
    val batteryPercent: Int? = null,
    val batteryCharging: Boolean? = null,
    val batteryHealth: String? = null,
    val temperatureC: Double? = null,
    val storageUsedGb: Double? = null,
    val storageTotalGb: Double? = null,
    val storageFreeGb: Double? = null,
    val ramUsedGb: Double? = null,
    val ramTotalGb: Double? = null,
    val networkType: String = "unknown",
    val networkConnected: Boolean = false,
    val wifiSsid: String? = null,
    val vpnActive: Boolean = false,
    val sdkInt: Int = 0,
    val manufacturer: String = "",
    val model: String = "",
    val osRelease: String = "",
    val uptimeHours: Long = 0,
)

@Serializable
data class NetworkProbe(
    val host: String,
    val reachable: Boolean,
    val resolvedAddresses: List<String> = emptyList(),
    val dnsMs: Long? = null,
    val tcpPort: Int? = null,
    val tcpConnectMs: Long? = null,
    val tlsVersion: String? = null,
    val tlsCipher: String? = null,
    val tlsSubject: String? = null,
    val tlsIssuer: String? = null,
    val tlsNotAfter: String? = null,
    val certificateChainLength: Int? = null,
    val error: String? = null,
)
