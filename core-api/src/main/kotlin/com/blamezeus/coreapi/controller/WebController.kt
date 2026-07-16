package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.service.QueryService
import org.springframework.stereotype.Controller
import org.springframework.ui.Model
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestParam

// Thin view over the existing QueryService.handle() entry point (Stage 9 Track B) — the same
// method QueryController.query already calls. No new orchestration, no new query logic.
@Controller
class WebController(
    private val queryService: QueryService,
) {

    @GetMapping("/")
    fun index(): String = "index"

    @PostMapping("/web/query")
    fun query(@RequestParam question: String, model: Model): String {
        model.addAttribute("question", question)
        model.addAttribute("response", queryService.handle(question))
        return "index"
    }
}
