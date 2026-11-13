package com.jarvisblue.core.common

import java.text.Normalizer
import java.util.Locale

object TextTools {

    /** Lowercase, strip accents and collapse punctuation — used for fuzzy matching. */
    fun normalize(input: String): String {
        val lower = input.lowercase(Locale.ROOT).trim()
        val decomposed = Normalizer.normalize(lower, Normalizer.Form.NFD)
        val noMarks = decomposed.replace(COMBINING_MARKS, "")
        return noMarks.replace(NON_ALPHANUMERIC, " ").replace(WHITESPACE, " ").trim()
    }

    fun tokens(input: String): List<String> =
        normalize(input).split(' ').filter { it.isNotEmpty() }

    /** Jaccard similarity over token sets, 0.0 .. 1.0. */
    fun similarity(a: String, b: String): Double {
        val setA = tokens(a).toSet()
        val setB = tokens(b).toSet()
        if (setA.isEmpty() && setB.isEmpty()) return 1.0
        if (setA.isEmpty() || setB.isEmpty()) return 0.0
        val intersection = setA.intersect(setB).size
        val union = setA.union(setB).size
        return intersection.toDouble() / union.toDouble()
    }

    fun levenshtein(a: String, b: String): Int {
        if (a == b) return 0
        if (a.isEmpty()) return b.length
        if (b.isEmpty()) return a.length
        var previous = IntArray(b.length + 1) { it }
        var current = IntArray(b.length + 1)
        for (i in 1..a.length) {
            current[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                current[j] = minOf(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + cost,
                )
            }
            val swap = previous; previous = current; current = swap
        }
        return previous[b.length]
    }

    /** Similarity tolerant of ASR noise: blends token overlap with edit distance. */
    fun fuzzySimilarity(a: String, b: String): Double {
        val na = normalize(a)
        val nb = normalize(b)
        if (na.isEmpty() && nb.isEmpty()) return 1.0
        if (na.isEmpty() || nb.isEmpty()) return 0.0
        val maxLen = maxOf(na.length, nb.length)
        val editSim = 1.0 - (levenshtein(na, nb).toDouble() / maxLen.toDouble())
        return (similarity(a, b) * 0.55 + editSim.coerceIn(0.0, 1.0) * 0.45).coerceIn(0.0, 1.0)
    }

    fun truncate(input: String, max: Int): String =
        if (input.length <= max) input else input.take(max - 1) + "…"

    private val COMBINING_MARKS = Regex("\\p{InCombiningDiacriticalMarks}+")
    private val NON_ALPHANUMERIC = Regex("[^\\p{L}\\p{N}\\s]+")
    private val WHITESPACE = Regex("\\s+")
}
