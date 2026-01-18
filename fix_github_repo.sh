#!/bin/bash

# Fix GitHub Repository - Replace with Current PC Files Only
# This will make GitHub match exactly what's on your PC

echo "🔄 Fixing GitHub repository to match your PC files..."

# Step 1: Remove .git to start fresh
rm -rf .git

# Step 2: Initialize new git repo
git init

# Step 3: Add all current files (only what's on your PC)
git add .

# Step 4: Create initial commit
git commit -m "Clean repository - enhanced watch system with vector search"

# Step 5: Add remote
git remote add origin https://github.com/AyushDoCode/WhatsappChatbot.git

# Step 6: Force push to replace everything on GitHub
git push --force-with-lease origin master

echo "✅ GitHub repository now matches your PC files exactly!"
echo "🎯 Repository contains only your enhanced watch system files"