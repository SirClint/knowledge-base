import { execSync } from "child_process";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..");

/**
 * Playwright global setup — runs once before the entire test suite.
 *
 * Performs SURGICAL cleanup: only removes data flagged as Playwright-owned.
 *
 * Two cleanup passes:
 *   1. playwright-*@example.com users and all docs they own.
 *      All Playwright test users are registered as playwright-<timestamp>-<rand>@example.com (see helpers.ts).
 *      All docs created by those users have owner set to their email, so they are identifiable.
 *   2. Docs with a blank owner — these are orphaned records that cannot be attributed to any real
 *      user. They should not exist in a correctly running system; cleaning them prevents test
 *      residue from accumulating if owner tracking ever regresses.
 *
 * Real user accounts (non-playwright-*, non-blank owner) are never touched.
 */
export default async function globalSetup() {
  console.log("\n[globalSetup] Cleaning up Playwright test data (playwright-*@example.com)...");

  const resetPy = `
import asyncio
from pathlib import Path
from db.database import async_session_maker
from db.models import Document, DocVersion, Comment
from auth.users import User
from sqlalchemy import select, delete

async def reset():
    async with async_session_maker() as session:
        # Pass 1: playwright-*@example.com users and their docs
        result = await session.execute(
            select(User.email).where(User.email.like('playwright-%@example.com'))
        )
        test_emails = [r[0] for r in result.fetchall()]

        owned_paths = []
        if test_emails:
            result = await session.execute(
                select(Document.path).where(Document.owner.in_(test_emails))
            )
            owned_paths = [r[0] for r in result.fetchall()]

        # Pass 2: docs with blank owner (orphaned — no real user can claim them)
        result = await session.execute(
            select(Document.path).where(Document.owner == '')
        )
        blank_paths = [r[0] for r in result.fetchall()]

        all_paths = list(set(owned_paths + blank_paths))

        # Delete vault files
        vault = Path('/vault')
        for doc_path in all_paths:
            f = vault / doc_path
            if f.exists():
                f.unlink()

        # Delete DB records (cascade order)
        if all_paths:
            await session.execute(delete(Comment).where(Comment.doc_path.in_(all_paths)))
            await session.execute(delete(DocVersion).where(DocVersion.doc_path.in_(all_paths)))
        if owned_paths:
            await session.execute(delete(Document).where(Document.owner.in_(test_emails)))
        if blank_paths:
            await session.execute(delete(Document).where(Document.owner == ''))

        # Delete the test users themselves
        if test_emails:
            await session.execute(delete(User).where(User.email.like('playwright-%@example.com')))

        await session.commit()

        print(f'[globalSetup] Removed {len(test_emails)} test user(s), {len(owned_paths)} owned doc(s), {len(blank_paths)} orphaned doc(s).')

asyncio.run(reset())
`.trim();

  execSync(
    `docker compose -f docker-compose.test.yml --env-file .env.test exec -T api python -c "${resetPy.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`,
    { cwd: ROOT, stdio: "inherit" }
  );

  console.log("[globalSetup] Done.\n");
}
