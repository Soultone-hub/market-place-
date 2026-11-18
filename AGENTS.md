# Marketplace development conventions

## SOLID

- **Single responsibility.** Keep state transitions in the domain and HTTP handling in the API. Keep order and payment orchestration in separate services and SQLAlchemy queries in the repository.
- **Open/closed.** Keep workflow rules together so a new transition can be added where the existing rules are defined.
- **Liskov substitution.** Keep the same guarantees and error behavior when replacing a component behind a shared contract.
- **Interface segregation.** Give callers focused interfaces with the operations they use.
- **Dependency inversion.** Keep the state machine independent of FastAPI and SQLAlchemy. Inject a transaction through the focused interface each service needs.

Use abstractions where they clarify a responsibility or a dependency.

## Code and Git

- Use English for code, identifiers, and comments. Follow PEP 8 and the surrounding code style.
- Name modules after their responsibilities, such as `order_service.py` and `payment_service.py`.
- Record order updates and their audit entries in the same database transaction.
- Use short English branch names such as `feature/order-workflow`, `fix/payment-idempotency`, and `docs/design-note`.
- Make regular, focused commits with English Conventional Commit messages. Review the diff and run the relevant pytest tests before integrating changes into `main` through a pull request.
- Keep credentials in the local, ignored `.env` file or the environment. Run PostgreSQL integration tests against a dedicated test database.
