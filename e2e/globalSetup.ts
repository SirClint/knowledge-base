import { execSync } from "child_process";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..");

/**
 * Playwright global setup — runs once before the entire test suite.
 *
 * Performs SURGICAL cleanup: only removes data flagged as Playwright-owned.
 *
 * The flag is the email prefix "playwright-" on "@example.com":
 *   - All Playwright test users are registered as playwright-<timestamp>-<rand>@example.com (see helpers.ts).
 *   - All docs created by those users (via UI or AI ingestion) have owner set
 *     to the user's email, so they are identifiable by the same prefix.
 *
 * Real user accounts and manually-preserved test data are untouched.
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
        # Find all Playwright test users (identified by playwright- prefix on @example.com)
        result = await session.execute(
            select(User.email).where(User.email.like('playwright-%@example.com'))
        )
        test_emails = [r[0] for r in result.fetchall()]

        if not test_emails:
            print('[globalSetup] No Playwright test users found (playwright-*@example.com) — nothing to clean up.')
            return

        # Find all docs owned by those users
        result = await session.execute(
            select(Document.path).where(Document.owner.in_(test_emails))
        )
        test_paths = [r[0] for r in result.fetchall()]

        # Delete vault files for those docs
        vault = Path('/vault')
        for doc_path in test_paths:
            f = vault / doc_path
            if f.exists():
                f.unlink()

        # Delete DB records owned by Playwright test users (cascade order)
        if test_paths:
            await session.execute(delete(Comment).where(Comment.doc_path.in_(test_paths)))
            await session.execute(delete(DocVersion).where(DocVersion.doc_path.in_(test_paths)))
            await session.execute(delete(Document).where(Document.owner.in_(test_emails)))

        # Delete the test users themselves
        await session.execute(delete(User).where(User.email.like('playwright-%@example.com')))
        await session.commit()

        print(f'[globalSetup] Removed {len(test_emails)} test user(s) and {len(test_paths)} test doc(s).')

asyncio.run(reset())
`.trim();

  execSync(
    `docker compose -f docker-compose.test.yml --env-file .env.test exec -T api python -c "${resetPy.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`,
    { cwd: ROOT, stdio: "inherit" }
  );

  console.log("[globalSetup] Done.\n");
}
