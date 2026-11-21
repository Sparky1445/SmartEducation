/* Small shared behaviours: copy buttons, flip cards, self-check quizzes. No framework. */
(function () {
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(b.dataset.copy).then(function () {
        var old = b.textContent; b.textContent = "Copied";
        setTimeout(function () { b.textContent = old; }, 1500);
      });
    });
  });

  document.querySelectorAll(".card").forEach(function (c) {
    c.addEventListener("click", function () {
      c.setAttribute("aria-pressed", c.getAttribute("aria-pressed") === "true" ? "false" : "true");
    });
  });

  document.querySelectorAll("[data-quiz]").forEach(function (quiz) {
    var total = quiz.querySelectorAll(".quiz__q").length, answered = 0, right = 0;
    var score = document.querySelector("[data-quiz-score]");
    quiz.querySelectorAll(".quiz__q").forEach(function (q) {
      var answer = parseInt(q.dataset.answer, 10);
      q.querySelectorAll("button.quiz__opt").forEach(function (opt) {
        opt.addEventListener("click", function () {
          if (q.classList.contains("is-done")) { return; }
          q.classList.add("is-done");
          var chosen = parseInt(opt.dataset.index, 10);
          opt.classList.add(chosen === answer ? "is-right" : "is-wrong");
          q.querySelectorAll("button.quiz__opt")[answer].classList.add("is-right");
          var why = q.querySelector(".quiz__why"); if (why) { why.hidden = false; }
          answered += 1; if (chosen === answer) { right += 1; }
          if (score) { score.textContent = right + " / " + total + (answered === total ? " · done" : ""); }
        });
      });
    });
  });
})();
