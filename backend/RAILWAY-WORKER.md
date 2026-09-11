# Railway AI worker rollout

The API and worker use the same repository and PostgreSQL database, but must be
separate Railway services. The worker does not need a public domain.

1. Deploy this revision to the existing web service. Production defaults to
   `AI_JOBS_ENABLED=false`, so the existing synchronous flow stays active while
   migration `009_durable_ai_jobs.sql` is applied.
2. In the same Railway project, choose **New → GitHub Repo**, select Roundtable,
   and name the service `Roundtable Worker`.
3. Set its root directory to `/backend`, its branch to `launch-prep`, and its
   custom start command to `python worker.py`.
4. Put it in the same region as the web and PostgreSQL services. Do not generate
   a public domain.
5. Configure these worker variables:

   ```text
   ENVIRONMENT=production
   DATABASE_BACKEND=postgres
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   LLM_BACKEND=live
   AI_JOB_GLOBAL_CONCURRENCY=4
   AI_JOB_USER_CONCURRENCY=1
   AI_JOB_WORKER_SLOTS=4
   AI_JOB_MAX_ATTEMPTS=3
   AI_JOB_LEASE_SECONDS=600
   AI_JOB_POLL_SECONDS=2
   ```

   Copy/reference the same LLM API keys and model-route variables used by the
   web service. OAuth, session, CORS, and Resend variables are not needed by the
   worker.
6. Deploy the worker. The web health endpoint should then report
   `"ai_worker_ready": true` and a positive `ai_worker_count`.
7. Only after the worker is ready, set `AI_JOBS_ENABLED=true` on the web service
   and redeploy it. Then publish the matching frontend build.

Rollback is immediate: set `AI_JOBS_ENABLED=false` on the web service. Already
queued/running jobs remain in PostgreSQL; the worker may finish them, and no job
data is lost.
