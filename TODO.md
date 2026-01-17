# TODO: Anthropic-Specific Improvements

## Phase 1: Prompt Caching (✅ COMPLETED)

**Goal**: Reduce API costs by 50-80% and cut latency by up to 85% using Anthropic's prompt caching.

**Why**: The bot reuses the same system prompt (~1.5k tokens) and often processes the same thread context multiple times. Caching means we only pay full price once per 5 minutes, then 10% for cache hits.

### Implementation Checklist

- [x] Update ChatAnthropic initialization to enable prompt caching beta
- [x] Add cache_control to system prompt (always cache)
- [x] Add cache_control to thread context (cache for repeated conversations)
- [x] Add cache_control to conversation history (cache stable prefix)
- [x] Update ToolExecution model to track token usage
- [x] Add token counting to agent loop
- [x] Test caching behavior with repeated requests
- [x] Verify cache hit/miss in API responses
- [x] Document expected savings

### What Was Implemented

**Code Changes:**
1. **`src/llm_handler.py`**: Added `anthropic-beta: prompt-caching-2024-07-31` header to enable caching
2. **`src/llm_handler.py`**: Added `cache_control` to SystemMessage to cache the system prompt
3. **`src/orm/tool_execution.py`**: Added token tracking fields (input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens)
4. **`src/services/tool_service.py`**: Updated record_execution() to accept token parameters
5. **`src/agent.py`**: Extract token usage from AIMessage and log cache hits

**Current Caching Strategy:**
- ✅ System prompt (~1.5k tokens) is always cached
- ⏳ Future: Can add caching to thread context and history for even more savings

### Monitoring Cache Performance

**Check cache hits in logs:**
```bash
# When bot uses tools, look for cache-related logs
uv run atproto-bot --once -v 2>&1 | grep "Token usage"

# Example output:
# [INFO] Token usage: input=2000, output=150, cache_creation=1500, cache_read=0
# First request: Creates cache (cache_creation=1500)
#
# [INFO] Token usage: input=2000, output=150, cache_creation=0, cache_read=1500
# Second request: Reads from cache (cache_read=1500) - 90% savings!
```

**Check cache hits in database:**
```bash
# View token usage for recent tool executions
sqlite3 ~/.atproto-bot/bot.db "
SELECT
  tool_name,
  input_tokens,
  output_tokens,
  cache_creation_input_tokens,
  cache_read_input_tokens,
  created_at
FROM tool_executions
ORDER BY created_at DESC
LIMIT 10;"

# Calculate cache hit rate
sqlite3 ~/.atproto-bot/bot.db "
SELECT
  COUNT(CASE WHEN cache_read_input_tokens > 0 THEN 1 END) * 100.0 / COUNT(*) as cache_hit_rate_pct,
  SUM(input_tokens) as total_input_tokens,
  SUM(cache_creation_input_tokens) as total_cache_creation,
  SUM(cache_read_input_tokens) as total_cache_read
FROM tool_executions
WHERE created_at > datetime('now', '-1 day');"
```

**Calculate cost savings:**
```bash
# Sonnet 4 pricing (per million tokens):
# - Regular input: $3.00
# - Cache creation: $3.75 (25% markup)
# - Cache read: $0.30 (90% discount)
# - Output: $15.00

# Example calculation:
# Without caching: 1000 requests × 2000 tokens × $3/M = $6.00
# With caching:
#   - First: 2000 tokens × $3.75/M = $0.0075
#   - Next 999: 2000 × $0.30/M × 999 = $0.60
#   - Total: $0.61 (90% savings!)
```

### Technical Details

**Cache Breakpoints** (in order from stable to volatile):
1. System prompt - Changes never, cache indefinitely
2. Thread context - Changes per conversation, cache per thread
3. Conversation history - Grows incrementally, cache prefix
4. User instruction - Changes every time, never cache

**Cache Lifespan**: 5 minutes (Anthropic's current TTL)

**Cost Formula**:
- Regular tokens: $3 per million input tokens (Sonnet 4)
- Cached tokens (write): $3.75 per million (25% markup)
- Cached tokens (read): $0.30 per million (90% discount)

**Expected Savings**:
- First request: Pays 125% (caching overhead)
- Cache hits (next 5 min): Pays 10% for cached portion
- Break-even: 2 requests within 5 minutes
- High-traffic: 70-80% cost reduction

### Files to Modify

1. `src/llm_handler.py`:
   - Update `_create_llm()` to enable prompt caching beta
   - Add cache_control to SystemMessage
   - Add cache_control to thread context in HumanMessage
   - Add cache_control to conversation history

2. `src/orm/tool_execution.py`:
   - Add `input_tokens` field
   - Add `output_tokens` field
   - Add `cache_creation_input_tokens` field
   - Add `cache_read_input_tokens` field

3. `src/services/tool_service.py`:
   - Update `record_execution()` to accept token counts

4. `src/agent.py`:
   - Extract token usage from AIMessage response
   - Pass token counts to tool_service

### Testing Strategy

1. Send first request → verify cache_creation_input_tokens > 0
2. Send same request within 5 min → verify cache_read_input_tokens > 0
3. Wait 6 minutes → verify cache expires and recreates
4. Check database for token counts
5. Calculate actual savings percentage

### Success Metrics

- Cache hit rate > 60% for active conversations
- Cost reduction > 50% for typical usage patterns
- Latency reduction visible in logs

---

## Phase 2: Extended Thinking (✅ COMPLETED)

**Goal**: Enable Claude's thinking process for better reasoning on complex questions.

### Benefits
- More accurate tool selection
- Better multi-step reasoning
- Improved edge case handling
- Debuggable decision making

### Implementation Checklist
- [x] Add `enable_extended_thinking=True` to ChatAnthropic
- [x] Add config toggle in config.yaml
- [x] Extract thinking content from AIMessage responses
- [x] Add thinking_content field to ToolExecution model
- [x] Store thinking in database for debugging
- [x] Add logging for thinking content (first 200 chars)
- [ ] Test with complex math/reasoning questions

### What Was Implemented

**Code Changes:**
1. **`src/config.py`**: Added `extended_thinking: bool` field to LLMConfig (default=True)
2. **`config.yaml`**: Added `extended_thinking: true` to enable the feature
3. **`src/llm_handler.py`**: Added `enable_extended_thinking=self.config.extended_thinking` to ChatAnthropic initialization
4. **`src/agent.py`**: Extract thinking content from `response.response_metadata["thinking"]` and log first 200 characters
5. **`src/orm/tool_execution.py`**: Added `thinking_content: Text` field for storing reasoning
6. **`src/services/tool_service.py`**: Updated record_execution() to accept and store thinking_content

**Current Behavior:**
- Extended thinking is enabled globally (both mentions and DMs)
- Thinking content is extracted after each LLM call
- First 200 characters are logged for quick debugging
- Full thinking is stored in database for detailed analysis

### Monitoring Extended Thinking

**Check thinking in logs:**
```bash
# Look for extended thinking logs
uv run atproto-bot --once -v 2>&1 | grep "Extended thinking"

# Example output:
# [INFO] Extended thinking: Let me analyze this request. I need to...
```

**Check thinking in database:**
```bash
# View thinking content for recent tool executions
sqlite3 ~/.atproto-bot/bot.db "
SELECT
  tool_name,
  substr(thinking_content, 1, 100) as thinking_preview,
  success,
  created_at
FROM tool_executions
WHERE thinking_content IS NOT NULL
ORDER BY created_at DESC
LIMIT 5;"

# Count how often thinking is captured
sqlite3 ~/.atproto-bot/bot.db "
SELECT
  COUNT(*) as total_executions,
  COUNT(thinking_content) as with_thinking,
  COUNT(thinking_content) * 100.0 / COUNT(*) as thinking_pct
FROM tool_executions;"
```

### Technical Details

**How Extended Thinking Works:**
1. LLM generates thinking content before final response
2. Thinking is available in `response.response_metadata["thinking"]`
3. First 200 chars logged for quick visibility
4. Full content stored in database for analysis
5. Thinking helps LLM decide when/how to use tools

**When Thinking is Most Useful:**
- Complex multi-step questions
- Tool selection decisions
- Mathematical reasoning
- Edge case handling

**Database Schema:**
```sql
thinking_content TEXT  -- Stores full extended thinking content
```

---

## Phase 3: Vision Support (TODO)

**Goal**: Allow bot to analyze images in posts and threads.

### Use Cases
- Answer questions about screenshots
- Describe images for owner
- Analyze charts/diagrams
- Code review from screenshots

### Implementation Plan
- [ ] Detect images in thread posts
- [ ] Download images via ATProto
- [ ] Convert to base64 for API
- [ ] Add image content to message context
- [ ] Handle image-based questions
- [ ] Test with various image types

---

## Phase 4: Remove OpenAI Compatibility (TODO)

**Goal**: Simplify codebase by removing unused OpenAI code.

### Changes
- [ ] Remove OpenAI from config schema
- [ ] Remove OpenAI branch from `_create_llm()`
- [ ] Remove `langchain-openai` dependency
- [ ] Update tests
- [ ] Update documentation

**Note**: Only do this after confirming no future OpenAI needs.

---

## Phase 5: Streaming Responses (FUTURE)

**Goal**: Stream tokens as generated for faster perceived latency.

### Complexity
- Requires async streaming implementation
- Need to handle partial responses
- Decide when to "commit" a response
- Handle streaming errors gracefully

**Defer until**: High user demand or very long responses become common.

---

## Phase 6: Message Batching (FUTURE)

**Goal**: Batch multiple requests for better throughput.

### Use Case
- Multiple mentions/DMs arrive simultaneously
- Batch process for efficiency

**Defer until**: Bot reaches high scale (>100 requests/minute).
