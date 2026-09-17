from __future__ import annotations

import argparse
import sys
import uuid
from datetime import UTC, datetime, timedelta

from .auth import AuthSession, AuthenticationError, authenticate
from .config import Config
from .json_repository import JsonRepository, RepositoryError
from .models import QuestionAnswer
from .official_cli import OfficialCliClient, OfficialCliError
from .workiq_client import WorkIQClient, WorkIQError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workiq-exporter")
    commands = parser.add_subparsers(dest="command", required=True)
    ask = commands.add_parser("ask", help="Ask Work IQ and optionally save the answer")
    ask.add_argument("question", nargs="?", help="Question; prompted when omitted")
    ask.add_argument("--context-id", help="Context ID for an explicit follow-up")
    commands.add_parser("list", help="List saved question and answer pairs")
    show = commands.add_parser("show", help="Show one saved pair")
    show.add_argument("id")
    delete = commands.add_parser("delete", help="Delete one saved pair")
    delete.add_argument("id")
    purge = commands.add_parser("purge", help="Delete saved pairs")
    purge.add_argument("--all", action="store_true", help="Delete every local pair without signing in")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.from_environment(require_identity=not (args.command == "purge" and args.all))
        repository = JsonRepository(config.data_path)
        if args.command == "purge" and args.all:
            print(f"Deleted {repository.purge()} local item(s).")
            return 0
        if config.provider == "official-cli":
            auth = AuthSession("", config.tenant_id, config.account)
        else:
            auth = authenticate(config.tenant_id, config.client_id)
        if args.command == "ask":
            return _ask(args, config, repository, auth)
        if args.command == "list":
            for item in repository.list_for(auth.tenant_id, auth.user_oid):
                question_preview = item.question.replace("\n", " ")[:80]
                answer_preview = item.answer.replace("\n", " ")[:120]
                print(
                    f"{item.id}  {item.generated_at}\n"
                    f"  Question: {question_preview}\n"
                    f"  Answer: {answer_preview}"
                )
            return 0
        if args.command == "show":
            item = repository.get(args.id, auth.tenant_id, auth.user_oid)
            if item is None:
                print("Item not found.", file=sys.stderr)
                return 1
            print(f"Question: {item.question}\n\nAnswer: {item.answer}")
            for citation in item.citations:
                print(f"Citation: {citation.title or ''} {citation.url or ''}".rstrip())
            return 0
        if args.command == "delete":
            deleted = repository.delete(args.id, auth.tenant_id, auth.user_oid)
            print("Deleted." if deleted else "Item not found.")
            return 0 if deleted else 1
        deleted = repository.purge(auth.tenant_id, auth.user_oid)
        print(f"Deleted {deleted} item(s).")
        return 0
    except (
        AuthenticationError,
        OfficialCliError,
        RepositoryError,
        WorkIQError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _ask(
    args: argparse.Namespace,
    config: Config,
    repository: JsonRepository,
    auth: AuthSession,
) -> int:
    question = args.question or input("Question: ").strip()
    client = (
        OfficialCliClient(config.account)
        if config.provider == "official-cli"
        else WorkIQClient(auth.access_token)
    )
    answer = client.ask(
        question,
        time_zone=config.time_zone,
        context_id=args.context_id,
    )
    print(f"\n{answer.text}")
    for citation in answer.citations:
        print(f"Citation: {citation.title or ''} {citation.url or ''}".rstrip())
    if answer.context_id:
        print(f"Context ID: {answer.context_id}")
    if input("\nSave this question and answer locally? [y/N] ").strip().lower() != "y":
        print("Not saved.")
        return 0
    now = datetime.now(UTC)
    repository.add(
        QuestionAnswer(
            id=str(uuid.uuid4()),
            tenant_id=auth.tenant_id,
            user_oid=auth.user_oid,
            question=question,
            answer=answer.text,
            citations=answer.citations,
            context_id=answer.context_id,
            generated_at=now.isoformat(),
            expires_at=(now + timedelta(hours=config.retention_hours)).isoformat(),
        )
    )
    print(f"Saved to {repository.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
