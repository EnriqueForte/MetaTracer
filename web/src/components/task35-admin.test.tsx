import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { importKnowledgeFile, KnowledgeView, MAX_KB_BYTES } from "@/components/knowledge/knowledge-view";
import { parseHeaderLines, WebhooksView } from "@/components/webhooks/webhooks-view";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(role: "operator" | "viewer", webhooks: unknown[] = []) {
  const posts: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: true, username: "ada", role }), { status: 200 });
      }
      if (url.startsWith("/api/webhooks") && init?.method === "POST") {
        posts.push(JSON.parse(String(init.body)));
        return new Response("{}", { status: 201 });
      }
      if (url.startsWith("/api/webhooks")) return new Response(JSON.stringify(webhooks), { status: 200 });
      return new Response("{}", { status: 200 });
    }),
  );
  return posts;
}

describe("Webhooks screen (TASK-35)", () => {
  it("is operator-only", async () => {
    stub("viewer");
    render(<WebhooksView />);
    expect(await screen.findByText("Se requiere el rol de operador")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear webhook" })).not.toBeInTheDocument();
  });

  it("never shows header values or the secret, and refuses plain HTTP", async () => {
    const posts = stub("operator", [
      {
        id: "w1",
        name: "<b>alerts</b>",
        url: "https://hooks.example.com/wh",
        event: "completed",
        headers: { Authorization: "***" },
        max_retries: 3,
        active: true,
        signature_status: "active",
        created_at: "2026-10-01T10:00:00Z",
      },
    ]);
    render(<WebhooksView />);
    expect(await screen.findByText("<b>alerts</b>")).toBeInTheDocument();
    expect(screen.getByText("Cabeceras: Authorization (valores ocultos)")).toBeInTheDocument();
    expect(screen.getByText("Firmado (HMAC)")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();

    fireEvent.change(screen.getByLabelText("URL HTTPS"), { target: { value: "http://hooks.example.com/x" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear webhook" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Las URL de webhook deben usar HTTPS.");
    expect(posts).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("URL HTTPS"), { target: { value: "https://hooks.example.com/x" } });
    fireEvent.change(screen.getByLabelText("Secreto de firma (opcional)"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear webhook" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ url: "https://hooks.example.com/x", signature_secret: "s3cret" });
    await waitFor(() => expect(screen.getByLabelText("Secreto de firma (opcional)")).toHaveValue(""));
  });

  it("parses header lines strictly", () => {
    expect(parseHeaderLines("Authorization: Bearer x\nX-Team: red")).toEqual({ Authorization: "Bearer x", "X-Team": "red" });
    expect(typeof parseHeaderLines("no colon here")).toBe("string");
    expect(typeof parseHeaderLines("Bad Name: x")).toBe("string");
  });
});

describe("Knowledge screen (TASK-35)", () => {
  it("is operator-only", async () => {
    stub("viewer");
    render(<KnowledgeView />);
    expect(await screen.findByText("Se requiere el rol de operador")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Exportar precedentes" })).not.toBeInTheDocument();
  });

  it("checks size and JSON before uploading", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const big = new File(["{}"], "kb.json");
    Object.defineProperty(big, "size", { value: MAX_KB_BYTES + 1 });
    await expect(importKnowledgeFile(big)).rejects.toThrow("El fichero es demasiado grande");
    await expect(importKnowledgeFile(new File(["nope"], "kb.json"))).rejects.toThrow("no es JSON válido");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
