# Webhook Setup - Next Steps

The code has been deployed via GitHub Actions. Here are the remaining manual steps:

## 1. DNS Configuration

Add an A record for the webhook subdomain:

```
Type: A
Name: webhooks
Host: webhooks.vitorpy.com
Value: <VPS_IP_ADDRESS>
TTL: 300
```

You can get your VPS IP with:
```bash
ssh vitorpy@scherbius.vitorpy.com "curl -4 ifconfig.me"
```

## 2. Verify Deployment

SSH into the VPS and check the service status:

```bash
ssh vitorpy@scherbius.vitorpy.com

# Check service is running
sudo systemctl status atproto-bot

# Check logs for webhook server startup
sudo journalctl -u atproto-bot -n 100 | grep -E "webhook|combined"

# Should see:
# "Starting combined mode (polling + webhook)"
# "Starting webhook server on port 8080..."
```

## 3. Verify Webhook Server

Test the webhook server is responding:

```bash
# From your VPS
curl http://localhost:8080/health

# Should return:
# {"status":"healthy","service":"atproto-bot-webhooks"}
```

## 4. Verify Nginx

Check nginx configuration is active:

```bash
# From your VPS
sudo nginx -t

# Check nginx config is linked
ls -la /etc/nginx/sites-enabled/ | grep atproto

# Test health endpoint via nginx
curl https://webhooks.vitorpy.com/health
```

## 5. Configure GitHub App Webhooks

Go to your GitHub App settings:
https://github.com/settings/apps/atproto-bot-selfimprovement

Navigate to **Webhooks** section:

1. **Webhook URL:** `https://webhooks.vitorpy.com/webhooks/github`
2. **Webhook secret:** (already set in GitHub secrets as WEBHOOK_SECRET)
3. **SSL verification:** ✅ Enable
4. **Active:** ✅ Check
5. **Subscribe to events:**
   - ✅ Issue comments
   - ✅ Pull request review comments
6. **Save changes**

## 6. Test End-to-End

Create a test PR and comment on it:

```bash
# From Bluesky, send a message to the bot:
@assistant.vitorpy.com /selfimprovement add a comment to webhook_server.py

# Wait for bot to create PR, then:
# 1. Go to the PR on GitHub
# 2. Add a comment: "also add type hints"
# 3. Wait ~30 seconds
# 4. Verify new commit appears on the PR
# 5. Verify bot replies to your comment
```

## 7. Monitoring

Check webhook deliveries in GitHub:

1. Go to: https://github.com/settings/apps/atproto-bot-selfimprovement
2. Click **Advanced** → **Recent Deliveries**
3. Verify deliveries are showing green checkmarks (200 responses)

Check logs on VPS:

```bash
# Watch logs live
sudo journalctl -u atproto-bot -f

# Search for webhook events
sudo journalctl -u atproto-bot | grep "webhook"

# Check for errors
sudo journalctl -u atproto-bot | grep -i error
```

## 8. Database Verification

Check the new tables were created:

```bash
ssh vitorpy@scherbius.vitorpy.com

# List tables
sqlite3 /var/lib/atproto-bot/bot.db ".tables"

# Should see: pr_comments, pr_iterations

# Check schema
sqlite3 /var/lib/atproto-bot/bot.db "PRAGMA table_info(pr_iterations);"
```

## Troubleshooting

### Webhook server not starting

Check logs:
```bash
sudo journalctl -u atproto-bot -n 100 | grep -i error
```

Common issues:
- Port 8080 already in use: `sudo lsof -i :8080`
- Missing dependencies: Check if fastapi/uvicorn are installed in venv
- Config error: Verify GITHUB_WEBHOOK_SECRET is set in /etc/systemd/system/atproto-bot.env

### Nginx 502 Bad Gateway

Check if webhook server is listening:
```bash
sudo netstat -tlnp | grep 8080
# Should show python listening on 127.0.0.1:8080
```

### GitHub webhook failing signature verification

Check the webhook secret matches:
```bash
# On VPS
sudo cat /etc/systemd/system/atproto-bot.env | grep WEBHOOK_SECRET

# Should match the value in GitHub App settings
```

### No response to PR comments

Check:
1. Comment is on a PR created by the bot (via /selfimprovement)
2. Comment is from the owner (vitorpy)
3. Webhook was delivered (check GitHub webhook deliveries)
4. Check logs for processing: `sudo journalctl -u atproto-bot | grep "PR comment"`

## Rollback Plan

If webhooks fail, you can revert to polling-only mode:

```bash
# SSH to VPS
ssh vitorpy@scherbius.vitorpy.com

# Edit systemd service
sudo nano /etc/systemd/system/atproto-bot.service

# Change:
# ExecStart=... --mode combined --webhook-port 8080
# To:
# ExecStart=... --mode polling

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart atproto-bot

# Disable webhook in GitHub App settings
```

## Success Criteria

✅ Deployment successful when:
- Service shows "combined mode" in logs
- Health endpoint responds: `curl https://webhooks.vitorpy.com/health`
- GitHub webhook deliveries show 200 responses
- PR comment triggers bot response within 30 seconds
- New commits appear on PR branch
- Bot posts confirmation comment
- Database shows iteration records

## Current Status

- ✅ Code deployed via GitHub Actions
- ⏳ DNS configuration (manual step)
- ⏳ GitHub App webhook configuration (manual step)
- ⏳ End-to-end testing (manual step)

Webhook secret: a003ee7dda8d2ded0d7786984058629fbeca0b4b03d94c08ed19fbd7d6238a9d
