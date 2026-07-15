package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.conflict.ConflictClaim
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import org.springframework.stereotype.Component

// Stage 7 Track A2/C1, [DEVIATED - see DEVIATIONS.md #DEV-051]: a deterministic, non-`@AiService`
// mapper, not the LLM prose formatter IMPLEMENTATION_PLAN.md §5 describes. `conflicts[]`
// presentation is data-driven (ADR-007 §5): every fetched ConflictClaim is carried straight
// through to a ConflictEntry, in the order ConflictLookup returned it — no filtering, no
// reordering, no winner chosen, and no assertion (implicit or explicit) that the versions
// contradict each other (they may be complementary, e.g. one names a killer and another the
// manner of death).
@Component
class ConflictSynthesizer {

    fun synthesize(claims: List<ConflictClaim>): List<ConflictEntry> =
        claims.map {
            ConflictEntry(
                claimValue = it.claimValue,
                sourceAuthor = it.sourceAuthor,
                sourceWork = it.sourceWork,
                passageRef = it.passageRef,
            )
        }
}
