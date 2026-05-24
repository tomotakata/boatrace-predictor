#!/bin/bash
# Setup Vercel environment variables for boatrace-predictor

PROJECT="boatrace-predictor"
TEAM="otomopalcome-4921s-projects"

echo "Setting up Vercel environment variables for $PROJECT..."

# Add each env var
vercel env add SUPABASE_URL production --token "$VERCEL_TOKEN" <<< "$SUPABASE_URL"
vercel env add SUPABASE_KEY production --token "$VERCEL_TOKEN" <<< "$SUPABASE_KEY"
vercel env add ANTHROPIC_API_KEY production --token "$VERCEL_TOKEN" <<< "$ANTHROPIC_API_KEY"
vercel env add GOOGLE_API_KEY production --token "$VERCEL_TOKEN" <<< "$GOOGLE_API_KEY"
vercel env add BOATFRONTIER_EMAIL production --token "$VERCEL_TOKEN" <<< "$BOATFRONTIER_EMAIL"
vercel env add BOATFRONTIER_PASSWORD production --token "$VERCEL_TOKEN" <<< "$BOATFRONTIER_PASSWORD"

echo "Done!"
