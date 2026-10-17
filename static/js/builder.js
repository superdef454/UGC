// Конструктор опроса: собирает форму в json и отправляет в API.
// Порядок вопросов и вариантов = порядок элементов на странице.
(() => {
  const form = document.getElementById("builder");
  const list = document.getElementById("questions");
  const errorBox = document.getElementById("builder-error");
  const questionTemplate = document.getElementById("question-template");
  const optionTemplate = document.getElementById("option-template");

  const csrfToken = () => form.querySelector("[name=csrfmiddlewaretoken]").value;

  function renumber() {
    list.querySelectorAll(".builder__question").forEach((item, index) => {
      item.querySelector(".builder__number").textContent = `Вопрос ${index + 1}`;
    });
  }

  function addOption(question, text = "") {
    const option = optionTemplate.content.firstElementChild.cloneNode(true);
    option.querySelector("input").value = text;
    question.querySelector(".builder__options").append(option);
    return option;
  }

  function addQuestion() {
    const question = questionTemplate.content.firstElementChild.cloneNode(true);
    list.append(question);
    addOption(question);
    addOption(question);
    renumber();
    question.querySelector("[data-field=text]").focus();
  }

  // Кнопки внутри вопросов и вариантов - через делегирование.
  list.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const item = button.closest(".builder__option") || button.closest(".builder__question");

    if (button.dataset.addOption !== undefined) {
      addOption(button.closest(".builder__question")).querySelector("input").focus();
    } else if (button.dataset.remove !== undefined) {
      item.remove();
    } else if (button.dataset.move === "up" && item.previousElementSibling) {
      item.previousElementSibling.before(item);
    } else if (button.dataset.move === "down" && item.nextElementSibling) {
      item.nextElementSibling.after(item);
    }
    renumber();
  });

  function collect() {
    return {
      title: form.elements.title.value.trim(),
      description: form.elements.description.value.trim(),
      questions: [...list.querySelectorAll(".builder__question")].map((question) => ({
        text: question.querySelector("[data-field=text]").value.trim(),
        type: question.querySelector("[data-field=multiple]").checked ? "multiple" : "single",
        allow_custom_answer: question.querySelector("[data-field=custom]").checked,
        is_required: question.querySelector("[data-field=required]").checked,
        options: [...question.querySelectorAll("[data-field=option]")]
          .map((input) => input.value.trim())
          .filter(Boolean)
          .map((text) => ({ text })),
      })),
    };
  }

  // Ошибки DRF приходят вложенным json - достаём первое понятное сообщение.
  function firstError(data) {
    if (typeof data === "string") return data;
    if (Array.isArray(data)) return data.map(firstError).find(Boolean);
    if (data && typeof data === "object") return Object.values(data).map(firstError).find(Boolean);
    return null;
  }

  function describe(data) {
    if (data && data.questions && !Array.isArray(data.questions)) {
      const [index, detail] = Object.entries(data.questions)[0];
      return `Вопрос ${Number(index) + 1}: ${firstError(detail)}`;
    }
    return firstError(data);
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = collect();
    if (!payload.questions.length) {
      showError("Добавьте хотя бы один вопрос.");
      return;
    }

    const response = await fetch(form.dataset.api, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => null);

    if (!response.ok) {
      showError(describe(data) || "Не удалось сохранить опрос, попробуйте ещё раз.");
      return;
    }
    window.location.href = form.dataset.detail.replace("/0/", `/${data.id}/`);
  });

  document.getElementById("add-question").addEventListener("click", addQuestion);
  addQuestion();
})();
