"""Initial Chainlit data layer schema.

Revision ID: 001
Revises: None
Create Date: 2024-12-08

Creates tables for Chainlit's built-in data layer:
- User: User accounts
- Thread: Conversation threads
- Step: Messages and actions
- Element: File attachments
- Feedback: User ratings

Schema copied from official Chainlit migration:
https://github.com/Chainlit/chainlit-datalayer/blob/main/prisma/migrations/20250103173917_init_data_layer/migration.sql
https://github.com/Chainlit/chainlit-datalayer/blob/main/prisma/migrations/20250108095538_add_tags_to_thread/migration.sql
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    """Apply the initial Chainlit schema - exact copy from official migration."""

    # Enable pgcrypto extension for UUID generation
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Create StepType enum
    op.execute('''
        DO $$ BEGIN
            CREATE TYPE "StepType" AS ENUM (
                'assistant_message', 'embedding', 'llm', 'retrieval', 'rerank',
                'run', 'system_message', 'tool', 'undefined', 'user_message'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    ''')

    # User table
    op.execute('''
        CREATE TABLE IF NOT EXISTS "User" (
            "id" TEXT NOT NULL DEFAULT gen_random_uuid(),
            "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "metadata" JSONB NOT NULL,
            "identifier" TEXT NOT NULL,
            CONSTRAINT "User_pkey" PRIMARY KEY ("id")
        )
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS "User_identifier_idx" ON "User"("identifier")')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS "User_identifier_key" ON "User"("identifier")')

    # Thread table
    op.execute('''
        CREATE TABLE IF NOT EXISTS "Thread" (
            "id" TEXT NOT NULL DEFAULT gen_random_uuid(),
            "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deletedAt" TIMESTAMP(3),
            "name" TEXT,
            "metadata" JSONB NOT NULL,
            "userId" TEXT,
            "tags" TEXT[] DEFAULT ARRAY[]::TEXT[],
            CONSTRAINT "Thread_pkey" PRIMARY KEY ("id")
        )
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS "Thread_createdAt_idx" ON "Thread"("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS "Thread_name_idx" ON "Thread"("name")')

    # Add foreign key for Thread -> User
    op.execute('''
        ALTER TABLE "Thread" ADD CONSTRAINT "Thread_userId_fkey"
        FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE
    ''')

    # Step table
    op.execute('''
        CREATE TABLE IF NOT EXISTS "Step" (
            "id" TEXT NOT NULL DEFAULT gen_random_uuid(),
            "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "parentId" TEXT,
            "threadId" TEXT,
            "input" TEXT,
            "metadata" JSONB NOT NULL,
            "name" TEXT,
            "output" TEXT,
            "type" "StepType" NOT NULL,
            "showInput" TEXT DEFAULT 'json',
            "isError" BOOLEAN DEFAULT false,
            "startTime" TIMESTAMP(3) NOT NULL,
            "endTime" TIMESTAMP(3) NOT NULL,
            CONSTRAINT "Step_pkey" PRIMARY KEY ("id")
        )
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_createdAt_idx" ON "Step"("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_endTime_idx" ON "Step"("endTime")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_parentId_idx" ON "Step"("parentId")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_startTime_idx" ON "Step"("startTime")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_threadId_idx" ON "Step"("threadId")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_type_idx" ON "Step"("type")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_name_idx" ON "Step"("name")')
    op.execute('CREATE INDEX IF NOT EXISTS "Step_threadId_startTime_endTime_idx" ON "Step"("threadId", "startTime", "endTime")')

    # Add foreign keys for Step
    op.execute('''
        ALTER TABLE "Step" ADD CONSTRAINT "Step_parentId_fkey"
        FOREIGN KEY ("parentId") REFERENCES "Step"("id") ON DELETE CASCADE ON UPDATE CASCADE
    ''')
    op.execute('''
        ALTER TABLE "Step" ADD CONSTRAINT "Step_threadId_fkey"
        FOREIGN KEY ("threadId") REFERENCES "Thread"("id") ON DELETE CASCADE ON UPDATE CASCADE
    ''')

    # Element table
    op.execute('''
        CREATE TABLE IF NOT EXISTS "Element" (
            "id" TEXT NOT NULL DEFAULT gen_random_uuid(),
            "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "threadId" TEXT,
            "stepId" TEXT NOT NULL,
            "metadata" JSONB NOT NULL,
            "mime" TEXT,
            "name" TEXT NOT NULL,
            "objectKey" TEXT,
            "url" TEXT,
            "chainlitKey" TEXT,
            "display" TEXT,
            "size" TEXT,
            "language" TEXT,
            "page" INTEGER,
            "props" JSONB,
            CONSTRAINT "Element_pkey" PRIMARY KEY ("id")
        )
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS "Element_stepId_idx" ON "Element"("stepId")')
    op.execute('CREATE INDEX IF NOT EXISTS "Element_threadId_idx" ON "Element"("threadId")')

    # Add foreign keys for Element
    op.execute('''
        ALTER TABLE "Element" ADD CONSTRAINT "Element_stepId_fkey"
        FOREIGN KEY ("stepId") REFERENCES "Step"("id") ON DELETE CASCADE ON UPDATE CASCADE
    ''')
    op.execute('''
        ALTER TABLE "Element" ADD CONSTRAINT "Element_threadId_fkey"
        FOREIGN KEY ("threadId") REFERENCES "Thread"("id") ON DELETE CASCADE ON UPDATE CASCADE
    ''')

    # Feedback table
    op.execute('''
        CREATE TABLE IF NOT EXISTS "Feedback" (
            "id" TEXT NOT NULL DEFAULT gen_random_uuid(),
            "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "stepId" TEXT,
            "name" TEXT NOT NULL,
            "value" DOUBLE PRECISION NOT NULL,
            "comment" TEXT,
            CONSTRAINT "Feedback_pkey" PRIMARY KEY ("id")
        )
    ''')
    op.execute('CREATE INDEX IF NOT EXISTS "Feedback_createdAt_idx" ON "Feedback"("createdAt")')
    op.execute('CREATE INDEX IF NOT EXISTS "Feedback_name_idx" ON "Feedback"("name")')
    op.execute('CREATE INDEX IF NOT EXISTS "Feedback_stepId_idx" ON "Feedback"("stepId")')
    op.execute('CREATE INDEX IF NOT EXISTS "Feedback_value_idx" ON "Feedback"("value")')
    op.execute('CREATE INDEX IF NOT EXISTS "Feedback_name_value_idx" ON "Feedback"("name", "value")')

    # Add foreign key for Feedback
    op.execute('''
        ALTER TABLE "Feedback" ADD CONSTRAINT "Feedback_stepId_fkey"
        FOREIGN KEY ("stepId") REFERENCES "Step"("id") ON DELETE SET NULL ON UPDATE CASCADE
    ''')


def downgrade() -> None:
    """Remove all Chainlit tables."""
    op.execute('DROP TABLE IF EXISTS "Feedback" CASCADE')
    op.execute('DROP TABLE IF EXISTS "Element" CASCADE')
    op.execute('DROP TABLE IF EXISTS "Step" CASCADE')
    op.execute('DROP TABLE IF EXISTS "Thread" CASCADE')
    op.execute('DROP TABLE IF EXISTS "User" CASCADE')
    op.execute('DROP TYPE IF EXISTS "StepType"')
