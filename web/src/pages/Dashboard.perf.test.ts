import { describe, it, expect } from "vitest";
import type { MembershipInfo } from "../api/types";
import { sortMemberships, filterMemberships } from "./Dashboard";

// Mock data generator
function generateMemberships(count: number): MembershipInfo[] {
  const statuses = ["active", "ended", "paused"];
  const memberships: MembershipInfo[] = [];
  for (let i = 0; i < count; i++) {
    memberships.push({
      project_id: `p-${i}`,
      status: statuses[i % 3]!,
      display_name: `Project ${i}`,
      last_message_at: new Date(Date.now() - Math.random() * 10000000).toISOString(),
      last_message_preview: `Last message for project ${i}`,
    });
  }
  return memberships;
}

describe("Dashboard Performance Benchmark", () => {
  const DATA_SIZE = 50000; // Large enough to measure
  const memberships = generateMemberships(DATA_SIZE);
  const searchQueries = ["", "proj", "10", "message", "nothingmatches", "Project 1"];

  it("should benchmark baseline vs optimized for search updates", () => {
    console.log(`\nBenchmarking with ${DATA_SIZE} items...`);

    // --- BASELINE ---
    // The baseline re-sorts on every render (every search change)
    // We simulate this by calling sortMemberships inside the loop.
    // Note: sortMemberships uses array.filter which creates new arrays, so it's safe to call repeatedly.
    const startBaseline = performance.now();
    for (const q of searchQueries) {
      const sorted = sortMemberships(memberships);
      filterMemberships(sorted, q);
    }
    const endBaseline = performance.now();
    const baselineTime = endBaseline - startBaseline;

    // --- OPTIMIZED ---
    // The optimized version sorts ONCE (when memberships change), then filters on search change.

    const startOptimizedTotal = performance.now();

    // Step 1: Initial Sort (happens once)
    const sorted = sortMemberships(memberships);

    // Step 2: Search updates (happens for each query, using the already sorted result)
    const startSearchPhase = performance.now();
    for (const q of searchQueries) {
      filterMemberships(sorted, q);
    }
    const endOptimizedTotal = performance.now();

    const optimizedTotalTime = endOptimizedTotal - startOptimizedTotal;
    const optimizedSearchOnlyTime = endOptimizedTotal - startSearchPhase;

    console.log(`Baseline (Sort + Filter per query): ${baselineTime.toFixed(2)}ms`);
    console.log(`Optimized (Sort once + Filter per query): ${optimizedTotalTime.toFixed(2)}ms`);
    console.log(`Optimized (Search phase only): ${optimizedSearchOnlyTime.toFixed(2)}ms`);

    // Expectation: The optimized total time should be significantly less because we avoid sorting N-1 times.
    // The search phase only time should be very small.

    expect(optimizedTotalTime).toBeLessThan(baselineTime);
  });
});
