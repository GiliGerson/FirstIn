import { connection } from "next/server";
import JobFeed from "@/components/JobFeed";
import { demoJobs } from "@/lib/demoData";

/** Sample data is generated per request so relative times ("3 hours ago") stay fresh. */
async function sampleJobs() {
  await connection();
  return demoJobs(Date.now());
}

export default async function DemoJobsPage() {
  return <JobFeed initialJobs={await sampleJobs()} demo />;
}
