import type { Plugin } from "@opencode-ai/plugin"

export const ValidateJson: Plugin = async ({ $, worktree, client }) => {
  return {
    "tool.execute.after": async (input, _output) => {
      const tool = input.tool
      if (tool !== "write" && tool !== "edit") return

      const filePath = input.args?.filePath ?? input.args?.file_path
      if (!filePath || typeof filePath !== "string") return

      if (
        !filePath.startsWith("knowledge/articles/") ||
        !filePath.endsWith(".json")
      )
        return

      try {
        await $`python3 hooks/validate_json.py ${filePath}`.cwd(worktree).nothrow()
      } catch (err) {
        try {
          await client?.app?.log?.({
            body: {
              service: "validate-json",
              level: "error",
              message: `JSON validation hook crashed: ${err}`,
            },
          })
        } catch {
          // silently ignore logging failures
        }
      }
    },
  }
}
