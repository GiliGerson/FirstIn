import { connection } from "next/server";
import PipelineBoard from "@/components/PipelineBoard";
import { demoApplications } from "@/lib/demoData";

async function sampleApplications() {
  await connection();
  return demoApplications(Date.now());
}

export default async function DemoApplicationsPage() {
  return <PipelineBoard initialApps={await sampleApplications()} demo />;
}
