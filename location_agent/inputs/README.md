# RAG insights (the user's inputs, as text)

The team's RAG takes the user's inputs (coach observations, photos, voice memos, notes, strategy ideas) plus any venue documents, and returns **text insights**. Save that text here, one plain-text file per race day:

```
location_agent/inputs/<date>_rag_insights.txt      e.g. 2026-07-19_rag_insights.txt
```

- The strategist attaches the file to the AI request as `rag_insights`, next to the stored features.
- It's read on every run and is **not** part of the stored feature pack, so changing it never triggers a feature rebuild.
- If there's no file, the strategy is made from the features alone.
- The AI uses the text **as an input**, not something to check against the data:
  - facts, preferences and plans in it (e.g. "fog until 10:30", "start at the pin") go straight into the answers and the action plan
  - where the text differs from the forecast numbers, the strategy follows the text and lists the difference under uncertainty
  - it cites `rag_insights` when it uses the text
- **Backtest:** only give the RAG what was known on the race morning. Insights written with race-day hindsight would leak the answer into the test.
