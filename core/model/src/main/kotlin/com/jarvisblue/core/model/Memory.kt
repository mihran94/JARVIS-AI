package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

enum class MemoryKind {
    PROFILE, PREFERENCE, FACT, PROCEDURE, OBSERVATION, DOCUMENT_SUMMARY,
}

@Serializable
data class MemoryItem(
    val id: String,
    val kind: MemoryKind,
    val title: String,
    val body: String,
    val tags: List<String> = emptyList(),
    val source: String = "user",
    val createdAtEpochMs: Long = 0L,
    val lastAccessedEpochMs: Long = 0L,
    val accessCount: Int = 0,
    val pinned: Boolean = false,
    val embeddingReady: Boolean = false,
)
