#!/bin/bash
# Runtime validation script for UniOne Django

echo "🔍 Starting runtime validation..."

# 1. Check environment variables
if [ -f .env ]; then
    echo "✅ .env file found"
else
    echo "❌ .env file missing"
    exit 1
fi

# 2. Check Database connectivity and migrations
echo "⚙️ Checking database and migrations..."
python manage.py check
if [ $? -eq 0 ]; then
    echo "✅ Django system check passed"
else
    echo "❌ Django system check failed"
    exit 1
fi

# Check for pending migrations
MIGRATIONS_OUT=$(python manage.py showmigrations --plan | grep '\[ \]')
if [ -z "$MIGRATIONS_OUT" ]; then
    echo "✅ All migrations are applied"
else
    echo "❌ Pending migrations found:"
    echo "$MIGRATIONS_OUT"
    exit 1
fi

# 3. Run validation script for connectivity
python scripts/validate_env.py
if [ $? -eq 0 ]; then
    echo "✅ Connectivity checks passed"
else
    echo "❌ Connectivity checks failed"
    exit 1
fi

echo "🚀 Runtime validation: SUCCESS"
exit 0
