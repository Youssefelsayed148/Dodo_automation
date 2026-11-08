import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Empty, ErrorBox, Img, StatusTag } from "../components/ui";

export default function BooksPage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const books = useQuery({ queryKey: ["books"], queryFn: api.books });
  const create = useMutation({
    mutationFn: () => api.createBook({}),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["books"] });
      nav(`/books/${b.id}/source`);
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteBook(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["books"] }),
  });
  const restore = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.append("file", f);
      return api.importBackup(fd);
    },
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["books"] });
      nav(`/books/${b.id}/review`);
    },
  });

  return (
    <div className="stack">
      <div className="row">
        <h1 style={{ margin: 0 }}>{t("books.title")}</h1>
        <span className="spacer" />
        <button className="btn" onClick={() => fileRef.current?.click()} disabled={restore.isPending}>
          {t("books.import_backup")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          onChange={(e) => e.target.files?.[0] && restore.mutate(e.target.files[0])}
        />
        <button className="btn primary" onClick={() => create.mutate()} disabled={create.isPending}>
          + {t("books.new")}
        </button>
      </div>
      <ErrorBox error={books.error || create.error || remove.error || restore.error} />
      {books.isLoading && <div className="muted">{t("common.loading")}</div>}
      {books.data && books.data.length === 0 && (
        <Empty title={t("books.empty_title")}>
          <p className="muted">{t("books.empty_body")}</p>
          <button className="btn primary" onClick={() => create.mutate()}>
            + {t("books.new")}
          </button>
        </Empty>
      )}
      <div className="grid">
        {books.data?.map((b) => (
          <div className="card" key={b.id}>
            <Link to={`/books/${b.id}`} style={{ textDecoration: "none", color: "inherit" }}>
              {b.thumb_url ? (
                <div className="thumb" style={{ marginBlockEnd: 10, maxHeight: 220 }}>
                  <Img src={b.thumb_url} alt={b.title} />
                </div>
              ) : null}
              <h3>{b.title}</h3>
            </Link>
            <div className="row small">
              <StatusTag status={b.status} />
              <span className="muted">
                {t("books.pages_count", { count: b.page_count })} · {t(`lang.${b.book_language}`)}
              </span>
            </div>
            <div className="row" style={{ marginBlockStart: 10 }}>
              <Link className="btn small primary" to={`/books/${b.id}`}>
                {t("books.open")}
              </Link>
              <span className="spacer" />
              <button
                className="btn small danger"
                onClick={() => window.confirm(t("books.confirm_delete", { title: b.title })) && remove.mutate(b.id)}
              >
                {t("common.delete")}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
