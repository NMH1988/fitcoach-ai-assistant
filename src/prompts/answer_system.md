TODO (owner): the answer system prompt (O1) goes here; Claude reviews it (.claude/rules/workflow.md).

What the code around it already does, so the prompt can rely on it:
- The user message holds the retrieved chunks inside <sources>...</sources>, each starting with a
  label [S1]...[S6], the article title, year and evidence tier, then the chunk text.
- The user's question follows inside <user_input>...</user_input>.
- There are 1 to 6 sources, nearest to the question first; there can be fewer than 6.
- The app lists only the sources whose [S#] labels appear in the answer, so the model must cite
  with exactly these labels inside square brackets: [S1], [S1, S3], [S1; S3], [S1 and S3] or a
  range [S1-S3]. Other forms (S1 without brackets, [1], footnotes) are not read.
- Each turn stands alone: the model sees no earlier questions or answers and no user profile, so
  the prompt should not refer to them.
- Images in the answer are removed before it is shown (their URLs would load without a click).
- When no chunk is close enough to the question, the app answers with a fixed message and the
  model is not called; when the chunks given do not answer the question, the prompt should tell
  the model to say so and cite nothing.
- The answer is rendered as Markdown without HTML.
