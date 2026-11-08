<!-- prompt: qa_content v1 -->
Check the text content of these code-drawn book pages for correctness.

Language: {book_language}
Pages (JSON): {pages_json}

Check: spelling and grammar in the given language, questions have exactly one correct answer, words are age-appropriate, no brand or franchise names, no repeated pages.
{originality_rule}

Return {"ok": true|false, "issues": ["page N: problem", ...]}.
