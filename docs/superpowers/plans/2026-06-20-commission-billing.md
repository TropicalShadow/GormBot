# Commission Billing System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add commission lifecycle commands, multi-member assignment, and integrated billing with Stripe + crypto support.

**Architecture:** Extend existing schema with CommissionAssignment, Bill, and BotConfig tables. Add BillingSystem cog for payment commands and polling. ConfigSystem cog for runtime toggles.

**Tech Stack:** SQLAlchemy async, py-cord, Stripe API, aiohttp (for polling)

## Global Constraints

- Python 3.14+
- All DB operations async via SQLAlchemy async sessions
- Discord IDs stored as BigInteger
- Follow existing codebase patterns (see `db/`, `modules/`)
- Stripe keys from environment variables
- Crypto gateway interface abstract (implementation TBD)

## File Structure

```
db/
├── DatabaseSchema.py       # +CommissionAssignment, Bill, BotConfig models
├── CommissionConnection.py # +assignment methods
├── BillingConnection.py    # (new) Bill CRUD
├── ConfigConnection.py     # (new) BotConfig CRUD
├── __init__.py             # +exports

modules/
├── CommissionTracking.py   # +lifecycle commands, assign/unassign
├── BillingSystem.py        # (new) /bill commands, polling
├── ConfigSystem.py         # (new) /config commands

tests/
├── test_billing.py         # (new)
├── test_config.py          # (new)
├── test_commission.py      # (new)
```

---

### Task 1: Add Schema Models

**Files:**
- Modify: `db/DatabaseSchema.py:49-77`
- Modify: `db/__init__.py`

**Interfaces:**
- Consumes: Existing `Base`, `Commission` model
- Produces: `CommissionAssignment`, `Bill`, `BotConfig` models

- [ ] **Step 1: Write test for new models**

Create `tests/test_schema.py`:

```python
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.DatabaseSchema import (
    Base, Commission, CommissionAssignment, Bill, BotConfig,
    IndividualTicket, TicketCategory
)

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()

@pytest.mark.asyncio
async def test_commission_assignment_creation(session):
    ticket = IndividualTicket(
        channel_id=123, author_id=456, author_name="Test", category=TicketCategory.builder
    )
    session.add(ticket)
    await session.commit()

    comm = Commission(
        project_name="Test", budget="$100", brief="Brief", description="Desc",
        ticket_channel_id=123
    )
    session.add(comm)
    await session.commit()

    assignment = CommissionAssignment(
        commission_id=comm.id, member_id=789, member_name="Builder"
    )
    session.add(assignment)
    await session.commit()

    assert assignment.id is not None
    assert assignment.assigned_at is not None

@pytest.mark.asyncio
async def test_bill_creation(session):
    ticket = IndividualTicket(
        channel_id=100, author_id=200, author_name="Client", category=TicketCategory.builder
    )
    session.add(ticket)
    await session.commit()

    comm = Commission(
        project_name="Project", budget="$500", brief="Brief", description="Desc",
        ticket_channel_id=100
    )
    session.add(comm)
    await session.commit()

    bill = Bill(
        commission_id=comm.id, total_amount=500.00, currency="USD", deposit_percent=50
    )
    session.add(bill)
    await session.commit()

    assert bill.id is not None
    assert bill.deposit_paid is False
    assert bill.final_paid is False

@pytest.mark.asyncio
async def test_bot_config(session):
    config = BotConfig(key="stripe_enabled", value="true")
    session.add(config)
    await session.commit()

    result = await session.get(BotConfig, "stripe_enabled")
    assert result.value == "true"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: ImportError for CommissionAssignment, Bill, BotConfig

- [ ] **Step 3: Add models to DatabaseSchema.py**

Add after `Commission` class in `db/DatabaseSchema.py`:

```python
class CommissionAssignment(Base):
    __tablename__ = "commission_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission.id"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    member_name: Mapped[str] = mapped_column(String, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    commission: Mapped["Commission"] = relationship(
        "Commission", back_populates="assignments"
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission.id"), nullable=False
    )
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    deposit_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    deposit_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    final_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stripe_deposit_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_final_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    crypto_deposit_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    crypto_final_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    commission: Mapped["Commission"] = relationship(
        "Commission", back_populates="bills"
    )


class BotConfig(Base):
    __tablename__ = "bot_config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 4: Update imports in DatabaseSchema.py**

Add to imports at top:

```python
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
```

- [ ] **Step 5: Add relationships to Commission model**

Add to `Commission` class:

```python
    assignments: Mapped[list["CommissionAssignment"]] = relationship(
        "CommissionAssignment", back_populates="commission", cascade="all, delete-orphan"
    )
    bills: Mapped[list["Bill"]] = relationship(
        "Bill", back_populates="commission", cascade="all, delete-orphan"
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Update db/__init__.py exports**

```python
__all__ = (
    "TicketConnection", "DatabaseManager", "IndividualTicket", "TicketCategory",
    "Commission", "CommissionAssignment", "Bill", "BotConfig"
)

from .TicketConnection import TicketConnection
from .DatabaseManager import DatabaseManager
from .DatabaseSchema import (
    IndividualTicket, TicketCategory, Commission, CommissionAssignment, Bill, BotConfig
)
```

- [ ] **Step 8: Commit**

```bash
git add db/DatabaseSchema.py db/__init__.py tests/test_schema.py
git commit -m "feat: add CommissionAssignment, Bill, BotConfig models"
```

---

### Task 2: Add ConfigConnection

**Files:**
- Create: `db/ConfigConnection.py`
- Modify: `db/DatabaseManager.py`

**Interfaces:**
- Consumes: `BotConfig` model, `AsyncSession`
- Produces: `ConfigConnection` class with `get(key)`, `set(key, value)`, `get_all()`

- [ ] **Step 1: Write test for ConfigConnection**

Create `tests/test_config.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.DatabaseSchema import Base, BotConfig
from db.ConfigConnection import ConfigConnection

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()

@pytest.mark.asyncio
async def test_set_and_get_config(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    result = await conn.get("stripe_enabled")
    assert result == "true"

@pytest.mark.asyncio
async def test_get_missing_returns_none(session):
    conn = ConfigConnection(session)
    result = await conn.get("nonexistent")
    assert result is None

@pytest.mark.asyncio
async def test_set_overwrites(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    await conn.set("stripe_enabled", "false")
    result = await conn.get("stripe_enabled")
    assert result == "false"

@pytest.mark.asyncio
async def test_get_all(session):
    conn = ConfigConnection(session)
    await conn.set("stripe_enabled", "true")
    await conn.set("crypto_enabled", "false")
    result = await conn.get_all()
    assert result == {"stripe_enabled": "true", "crypto_enabled": "false"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: ImportError for ConfigConnection

- [ ] **Step 3: Create ConfigConnection.py**

Create `db/ConfigConnection.py`:

```python
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .DatabaseSchema import BotConfig


class ConfigConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        result = await self.session.get(BotConfig, key)
        return result.value if result else None

    async def set(self, key: str, value: str) -> None:
        existing = await self.session.get(BotConfig, key)
        if existing:
            existing.value = value
        else:
            self.session.add(BotConfig(key=key, value=value))
        await self.session.commit()

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(select(BotConfig))
        return {row.key: row.value for row in result.scalars().all()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Add config_session to DatabaseManager**

Add to `db/DatabaseManager.py`:

```python
from .ConfigConnection import ConfigConnection
```

And add method:

```python
    @asynccontextmanager
    async def config_session(self):
        async with self.session_factory() as session:
            yield ConfigConnection(session)
```

- [ ] **Step 6: Commit**

```bash
git add db/ConfigConnection.py db/DatabaseManager.py tests/test_config.py
git commit -m "feat: add ConfigConnection for runtime config"
```

---

### Task 3: Add BillingConnection

**Files:**
- Create: `db/BillingConnection.py`
- Modify: `db/DatabaseManager.py`

**Interfaces:**
- Consumes: `Bill` model, `AsyncSession`
- Produces: `BillingConnection` with `create_bill()`, `get_bill_by_commission()`, `get_unpaid_bills()`, `mark_deposit_paid()`, `mark_final_paid()`

- [ ] **Step 1: Write test for BillingConnection**

Create `tests/test_billing.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.DatabaseSchema import Base, Commission, IndividualTicket, TicketCategory, Bill
from db.BillingConnection import BillingConnection

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        ticket = IndividualTicket(
            channel_id=100, author_id=200, author_name="Client", category=TicketCategory.builder
        )
        sess.add(ticket)
        await sess.commit()
        comm = Commission(
            project_name="Test", budget="$500", brief="Brief", description="Desc",
            ticket_channel_id=100
        )
        sess.add(comm)
        await sess.commit()
        yield sess, comm.id
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_bill(session):
    sess, comm_id = session
    conn = BillingConnection(sess)
    bill = await conn.create_bill(comm_id, 500.00, "USD", 50)
    assert bill.id is not None
    assert bill.total_amount == 500.00
    assert bill.deposit_percent == 50

@pytest.mark.asyncio
async def test_get_bill_by_commission(session):
    sess, comm_id = session
    conn = BillingConnection(sess)
    await conn.create_bill(comm_id, 500.00, "USD", 50)
    bill = await conn.get_bill_by_commission(comm_id)
    assert bill is not None
    assert bill.total_amount == 500.00

@pytest.mark.asyncio
async def test_get_unpaid_bills(session):
    sess, comm_id = session
    conn = BillingConnection(sess)
    await conn.create_bill(comm_id, 500.00, "USD", 50)
    unpaid = await conn.get_unpaid_bills()
    assert len(unpaid) == 1

@pytest.mark.asyncio
async def test_mark_deposit_paid(session):
    sess, comm_id = session
    conn = BillingConnection(sess)
    bill = await conn.create_bill(comm_id, 500.00, "USD", 50)
    await conn.mark_deposit_paid(bill.id)
    updated = await conn.get_bill_by_commission(comm_id)
    assert updated.deposit_paid is True

@pytest.mark.asyncio
async def test_mark_final_paid(session):
    sess, comm_id = session
    conn = BillingConnection(sess)
    bill = await conn.create_bill(comm_id, 500.00, "USD", 50)
    await conn.mark_final_paid(bill.id)
    updated = await conn.get_bill_by_commission(comm_id)
    assert updated.final_paid is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_billing.py -v`
Expected: ImportError for BillingConnection

- [ ] **Step 3: Create BillingConnection.py**

Create `db/BillingConnection.py`:

```python
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .DatabaseSchema import Bill


class BillingConnection:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_bill(
        self,
        commission_id: int,
        total_amount: float,
        currency: str,
        deposit_percent: int
    ) -> Bill:
        bill = Bill(
            commission_id=commission_id,
            total_amount=total_amount,
            currency=currency,
            deposit_percent=deposit_percent
        )
        self.session.add(bill)
        await self.session.commit()
        return bill

    async def get_bill_by_commission(self, commission_id: int) -> Optional[Bill]:
        result = await self.session.execute(
            select(Bill).where(Bill.commission_id == commission_id)
        )
        return result.scalar_one_or_none()

    async def get_unpaid_bills(self) -> list[Bill]:
        result = await self.session.execute(
            select(Bill).where(
                or_(Bill.deposit_paid == False, Bill.final_paid == False)
            )
        )
        return list(result.scalars().all())

    async def mark_deposit_paid(self, bill_id: int) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.deposit_paid = True
            await self.session.commit()

    async def mark_final_paid(self, bill_id: int) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.final_paid = True
            await self.session.commit()

    async def set_stripe_deposit_id(self, bill_id: int, stripe_id: str) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.stripe_deposit_id = stripe_id
            await self.session.commit()

    async def set_stripe_final_id(self, bill_id: int, stripe_id: str) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.stripe_final_id = stripe_id
            await self.session.commit()

    async def set_crypto_deposit_id(self, bill_id: int, crypto_id: str) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.crypto_deposit_id = crypto_id
            await self.session.commit()

    async def set_crypto_final_id(self, bill_id: int, crypto_id: str) -> None:
        bill = await self.session.get(Bill, bill_id)
        if bill:
            bill.crypto_final_id = crypto_id
            await self.session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_billing.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Add billing_session to DatabaseManager**

Add import and method to `db/DatabaseManager.py`:

```python
from .BillingConnection import BillingConnection
```

```python
    @asynccontextmanager
    async def billing_session(self):
        async with self.session_factory() as session:
            yield BillingConnection(session)
```

- [ ] **Step 6: Commit**

```bash
git add db/BillingConnection.py db/DatabaseManager.py tests/test_billing.py
git commit -m "feat: add BillingConnection for bill management"
```

---

### Task 4: Add Assignment Methods to CommissionConnection

**Files:**
- Modify: `db/CommissionConnection.py`

**Interfaces:**
- Consumes: `CommissionAssignment` model
- Produces: `assign_member()`, `unassign_member()`, `get_assignments()`, `is_assigned()`

- [ ] **Step 1: Write test for assignment methods**

Create `tests/test_commission.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.DatabaseSchema import Base, Commission, IndividualTicket, TicketCategory
from db.CommissionConnection import CommissionConnection

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        ticket = IndividualTicket(
            channel_id=100, author_id=200, author_name="Client", category=TicketCategory.builder
        )
        sess.add(ticket)
        await sess.commit()
        comm = Commission(
            project_name="Test", budget="$500", brief="Brief", description="Desc",
            ticket_channel_id=100
        )
        sess.add(comm)
        await sess.commit()
        yield sess, comm.id
    await engine.dispose()

@pytest.mark.asyncio
async def test_assign_member(session):
    sess, comm_id = session
    conn = CommissionConnection(sess)
    await conn.assign_member(comm_id, 12345, "Builder")
    assignments = await conn.get_assignments(comm_id)
    assert len(assignments) == 1
    assert assignments[0].member_id == 12345

@pytest.mark.asyncio
async def test_unassign_member(session):
    sess, comm_id = session
    conn = CommissionConnection(sess)
    await conn.assign_member(comm_id, 12345, "Builder")
    await conn.unassign_member(comm_id, 12345)
    assignments = await conn.get_assignments(comm_id)
    assert len(assignments) == 0

@pytest.mark.asyncio
async def test_is_assigned(session):
    sess, comm_id = session
    conn = CommissionConnection(sess)
    assert await conn.is_assigned(comm_id, 12345) is False
    await conn.assign_member(comm_id, 12345, "Builder")
    assert await conn.is_assigned(comm_id, 12345) is True

@pytest.mark.asyncio
async def test_multiple_assignments(session):
    sess, comm_id = session
    conn = CommissionConnection(sess)
    await conn.assign_member(comm_id, 111, "Builder1")
    await conn.assign_member(comm_id, 222, "Builder2")
    assignments = await conn.get_assignments(comm_id)
    assert len(assignments) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_commission.py -v`
Expected: AttributeError for assign_member

- [ ] **Step 3: Add assignment methods to CommissionConnection**

Add import and methods to `db/CommissionConnection.py`:

```python
from .DatabaseSchema import Commission, CommissionAssignment
```

Add methods:

```python
    async def assign_member(self, commission_id: int, member_id: int, member_name: str) -> None:
        assignment = CommissionAssignment(
            commission_id=commission_id,
            member_id=member_id,
            member_name=member_name
        )
        self.session.add(assignment)
        await self.session.commit()

    async def unassign_member(self, commission_id: int, member_id: int) -> bool:
        result = await self.session.execute(
            select(CommissionAssignment).where(
                CommissionAssignment.commission_id == commission_id,
                CommissionAssignment.member_id == member_id
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            await self.session.delete(assignment)
            await self.session.commit()
            return True
        return False

    async def get_assignments(self, commission_id: int) -> list[CommissionAssignment]:
        result = await self.session.execute(
            select(CommissionAssignment).where(
                CommissionAssignment.commission_id == commission_id
            )
        )
        return list(result.scalars().all())

    async def is_assigned(self, commission_id: int, member_id: int) -> bool:
        result = await self.session.execute(
            select(CommissionAssignment).where(
                CommissionAssignment.commission_id == commission_id,
                CommissionAssignment.member_id == member_id
            )
        )
        return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_commission.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add db/CommissionConnection.py tests/test_commission.py
git commit -m "feat: add member assignment methods to CommissionConnection"
```

---

### Task 5: Add ConfigSystem Cog

**Files:**
- Create: `modules/ConfigSystem.py`

**Interfaces:**
- Consumes: `ConfigConnection`, `GormBot`
- Produces: `/config payments` command group

- [ ] **Step 1: Create ConfigSystem.py**

Create `modules/ConfigSystem.py`:

```python
from typing import cast, TYPE_CHECKING
import discord
from discord.ext.commands import Cog, Bot
from discord import (
    ApplicationContext,
    Permissions,
    SlashCommandGroup,
    Embed,
    Colour,
    option,
)

if TYPE_CHECKING:
    from utils import GormBot


class ConfigSystem(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    CONFIG_GROUP = SlashCommandGroup(
        name="config",
        description="Bot configuration",
        default_member_permissions=Permissions(administrator=True),
    )

    PAYMENTS_GROUP = CONFIG_GROUP.create_subgroup(
        name="payments",
        description="Payment provider configuration",
    )

    @PAYMENTS_GROUP.command(name="status")
    async def payments_status(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        async with bot.db.config_session() as config:
            stripe_enabled = await config.get("stripe_enabled") or "true"
            crypto_enabled = await config.get("crypto_enabled") or "true"

        embed = Embed(title="Payment Configuration", colour=Colour.blue())
        embed.add_field(
            name="Stripe",
            value="Enabled" if stripe_enabled == "true" else "Disabled",
            inline=True
        )
        embed.add_field(
            name="Crypto",
            value="Enabled" if crypto_enabled == "true" else "Disabled",
            inline=True
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @PAYMENTS_GROUP.command(name="stripe")
    @option("action", str, choices=["enable", "disable"])
    async def stripe_toggle(self, ctx: ApplicationContext, action: str):
        bot = cast("GormBot", ctx.bot)
        value = "true" if action == "enable" else "false"
        async with bot.db.config_session() as config:
            await config.set("stripe_enabled", value)
        await ctx.respond(f"Stripe payments {action}d.", ephemeral=True)

    @PAYMENTS_GROUP.command(name="crypto")
    @option("action", str, choices=["enable", "disable"])
    async def crypto_toggle(self, ctx: ApplicationContext, action: str):
        bot = cast("GormBot", ctx.bot)
        value = "true" if action == "enable" else "false"
        async with bot.db.config_session() as config:
            await config.set("crypto_enabled", value)
        await ctx.respond(f"Crypto payments {action}d.", ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(ConfigSystem(bot))
```

- [ ] **Step 2: Test manually (bot startup)**

Run: `uv run python main.py`
Check: Bot loads without errors, `/config payments status` responds

- [ ] **Step 3: Commit**

```bash
git add modules/ConfigSystem.py
git commit -m "feat: add ConfigSystem cog for payment toggles"
```

---

### Task 6: Add Commission Lifecycle Commands

**Files:**
- Modify: `modules/CommissionTracking.py`

**Interfaces:**
- Consumes: `CommissionConnection`, `Commission`, `CommissionStatus`
- Produces: `/commission start`, `complete`, `cancel`, `assign`, `unassign`, `info` commands

- [ ] **Step 1: Add imports to CommissionTracking.py**

Add to existing imports:

```python
from discord import Embed, Colour, Permissions, option, Member
from db.DatabaseSchema import Commission, CommissionStatus
```

- [ ] **Step 2: Add lifecycle commands**

Add to `CommissionTracking` class after existing commands:

```python
    @COMMISSION_SLASH_COMMAND_GROUP.command(name="start")
    async def start_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            if comm.status != CommissionStatus.open:
                await ctx.respond(f"Commission is already {comm.status.value}.", ephemeral=True)
                return
            comm.status = CommissionStatus.in_progress
            await session.upsert_comm(comm)

        await ctx.respond("Commission started! Status: **In Progress**")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="cancel")
    async def cancel_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            comm.status = CommissionStatus.cancelled
            await session.upsert_comm(comm)

        await ctx.respond("Commission cancelled.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="complete")
    async def complete_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)
            if bill and (not bill.deposit_paid or not bill.final_paid):
                await ctx.respond("Cannot complete: bill not fully paid.", ephemeral=True)
                return

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            comm.status = CommissionStatus.completed
            await session.upsert_comm(comm)

        await ctx.respond("Commission completed!")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="assign")
    @option("member", Member, description="Member to assign")
    async def assign_member(self, ctx: ApplicationContext, member: Member):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            if await session.is_assigned(comm.id, member.id):
                await ctx.respond(f"{member.display_name} is already assigned.", ephemeral=True)
                return
            await session.assign_member(comm.id, member.id, member.display_name)

        await ctx.respond(f"{member.display_name} assigned to commission.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="unassign")
    @option("member", Member, description="Member to unassign")
    async def unassign_member(self, ctx: ApplicationContext, member: Member):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            removed = await session.unassign_member(comm.id, member.id)
            if not removed:
                await ctx.respond(f"{member.display_name} is not assigned.", ephemeral=True)
                return

        await ctx.respond(f"{member.display_name} unassigned from commission.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="info")
    async def commission_info(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            assignments = await session.get_assignments(comm.id)

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)

        embed = Embed(title=f"Commission: {comm.project_name}", colour=Colour.blue())
        embed.add_field(name="Status", value=comm.status.value.replace("_", " ").title(), inline=True)
        embed.add_field(name="Budget", value=comm.budget, inline=True)
        embed.add_field(name="Brief", value=comm.brief, inline=False)

        if assignments:
            members = ", ".join(f"<@{a.member_id}>" for a in assignments)
            embed.add_field(name="Assigned", value=members, inline=False)
        else:
            embed.add_field(name="Assigned", value="No one", inline=False)

        if bill:
            deposit_amt = bill.total_amount * (bill.deposit_percent / 100)
            final_amt = bill.total_amount - deposit_amt
            bill_status = []
            bill_status.append(f"Deposit: ${deposit_amt:.2f} {'(Paid)' if bill.deposit_paid else '(Unpaid)'}")
            bill_status.append(f"Final: ${final_amt:.2f} {'(Paid)' if bill.final_paid else '(Unpaid)'}")
            embed.add_field(name="Bill", value="\n".join(bill_status), inline=False)
        else:
            embed.add_field(name="Bill", value="No bill created", inline=False)

        await ctx.respond(embed=embed)
```

- [ ] **Step 3: Test manually**

Run: `uv run python main.py`
Test: `/commission info`, `/commission start`, `/commission assign @user`

- [ ] **Step 4: Commit**

```bash
git add modules/CommissionTracking.py
git commit -m "feat: add commission lifecycle and assignment commands"
```

---

### Task 7: Add BillingSystem Cog

**Files:**
- Create: `modules/BillingSystem.py`

**Interfaces:**
- Consumes: `BillingConnection`, `ConfigConnection`, `Commission`
- Produces: `/bill create`, `status`, `confirm` commands, polling task

- [ ] **Step 1: Create BillingSystem.py**

Create `modules/BillingSystem.py`:

```python
from typing import cast, TYPE_CHECKING, Optional
import asyncio
from os import getenv
import discord
from discord.ext import tasks
from discord.ext.commands import Cog, Bot
from discord import (
    ApplicationContext,
    Embed,
    Colour,
    SlashCommandGroup,
    Permissions,
    option,
)

if TYPE_CHECKING:
    from utils import GormBot


class BillingSystem(Cog):
    def __init__(self, bot: Bot):
        self.bot: "GormBot" = bot
        self.stripe_api_key = getenv("STRIPE_SECRET_KEY")

    def cog_unload(self):
        self.poll_payments.cancel()

    @Cog.listener()
    async def on_ready(self):
        if not self.poll_payments.is_running():
            self.poll_payments.start()

    BILL_GROUP = SlashCommandGroup(
        name="bill",
        description="Billing management",
    )

    @BILL_GROUP.command(name="create")
    @option("amount", float, description="Total amount")
    @option("deposit_percent", int, description="Deposit percentage", default=50, min_value=0, max_value=100)
    async def create_bill(self, ctx: ApplicationContext, amount: float, deposit_percent: int = 50):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            existing = await billing.get_bill_by_commission(comm.id)
            if existing:
                await ctx.respond("Bill already exists. Use `/bill status` to view.", ephemeral=True)
                return
            bill = await billing.create_bill(comm.id, amount, "USD", deposit_percent)

        deposit_amt = amount * (deposit_percent / 100)
        final_amt = amount - deposit_amt

        embed = Embed(title="Bill Created", colour=Colour.green())
        embed.add_field(name="Total", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="Deposit", value=f"${deposit_amt:.2f} ({deposit_percent}%)", inline=True)
        embed.add_field(name="Final", value=f"${final_amt:.2f}", inline=True)

        async with bot.db.config_session() as config:
            stripe_enabled = (await config.get("stripe_enabled") or "true") == "true"
            crypto_enabled = (await config.get("crypto_enabled") or "true") == "true"

        payment_info = []
        if stripe_enabled:
            payment_info.append("**Stripe:** Payment link coming soon")
        if crypto_enabled:
            payment_info.append("**Crypto:** Payment address coming soon")
        if not payment_info:
            payment_info.append("No payment methods currently available.")

        embed.add_field(name="Payment Options", value="\n".join(payment_info), inline=False)

        await ctx.respond(embed=embed)

    @BILL_GROUP.command(name="status")
    async def bill_status(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)
            if not bill:
                await ctx.respond("No bill created yet. Use `/bill create`.", ephemeral=True)
                return

        deposit_amt = bill.total_amount * (bill.deposit_percent / 100)
        final_amt = bill.total_amount - deposit_amt

        embed = Embed(title="Bill Status", colour=Colour.blue())
        embed.add_field(name="Total", value=f"${bill.total_amount:.2f}", inline=True)
        embed.add_field(
            name="Deposit",
            value=f"${deposit_amt:.2f} {'✅' if bill.deposit_paid else '❌'}",
            inline=True
        )
        embed.add_field(
            name="Final",
            value=f"${final_amt:.2f} {'✅' if bill.final_paid else '❌'}",
            inline=True
        )

        await ctx.respond(embed=embed)

    CONFIRM_GROUP = BILL_GROUP.create_subgroup(
        name="confirm",
        description="Manual payment confirmation",
        default_member_permissions=Permissions(administrator=True),
    )

    @CONFIRM_GROUP.command(name="deposit")
    async def confirm_deposit(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)
            if not bill:
                await ctx.respond("No bill found.", ephemeral=True)
                return
            await billing.mark_deposit_paid(bill.id)

        await ctx.respond("Deposit marked as paid.", ephemeral=True)
        await ctx.channel.send(
            embed=Embed(
                title="Payment Received",
                description="Deposit payment confirmed.",
                colour=Colour.green()
            )
        )

    @CONFIRM_GROUP.command(name="final")
    async def confirm_final(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)
            if not bill:
                await ctx.respond("No bill found.", ephemeral=True)
                return
            await billing.mark_final_paid(bill.id)

        await ctx.respond("Final payment marked as paid.", ephemeral=True)
        await ctx.channel.send(
            embed=Embed(
                title="Payment Received",
                description="Final payment confirmed. Commission can now be completed.",
                colour=Colour.green()
            )
        )

    @tasks.loop(seconds=60)
    async def poll_payments(self):
        pass

    @poll_payments.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


def setup(bot: Bot):
    bot.add_cog(BillingSystem(bot))
```

- [ ] **Step 2: Test manually**

Run: `uv run python main.py`
Test: `/bill create 500 50`, `/bill status`, `/bill confirm deposit`

- [ ] **Step 3: Commit**

```bash
git add modules/BillingSystem.py
git commit -m "feat: add BillingSystem cog with bill commands"
```

---

### Task 8: Add Stripe Integration

**Files:**
- Modify: `modules/BillingSystem.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Stripe API, `BillingConnection`
- Produces: Payment link generation, polling implementation

- [ ] **Step 1: Add stripe dependency**

Run: `uv add stripe`

- [ ] **Step 2: Add Stripe payment link generation**

Add to `BillingSystem` class after imports:

```python
import stripe
```

Add method:

```python
    async def _create_stripe_payment_link(self, amount: float, description: str) -> Optional[str]:
        if not self.stripe_api_key:
            return None
        try:
            stripe.api_key = self.stripe_api_key
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": description},
                        "unit_amount": int(amount * 100),
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
            return session.url
        except Exception as e:
            self.bot.logger.error(f"Stripe error: {e}")
            return None
```

- [ ] **Step 3: Update create_bill to generate Stripe link**

Replace payment_info section in `create_bill`:

```python
        payment_info = []
        if stripe_enabled and self.stripe_api_key:
            link = await self._create_stripe_payment_link(
                deposit_amt, f"Deposit for {comm.project_name}"
            )
            if link:
                payment_info.append(f"**Stripe:** [Pay Deposit]({link})")
        if crypto_enabled:
            payment_info.append("**Crypto:** Contact for address")
        if not payment_info:
            payment_info.append("No payment methods available.")
```

- [ ] **Step 4: Implement polling**

Replace `poll_payments` method:

```python
    @tasks.loop(seconds=60)
    async def poll_payments(self):
        if not self.stripe_api_key:
            return

        try:
            stripe.api_key = self.stripe_api_key
            async with self.bot.db.billing_session() as billing:
                unpaid = await billing.get_unpaid_bills()

                for bill in unpaid:
                    if bill.stripe_deposit_id and not bill.deposit_paid:
                        try:
                            session = stripe.checkout.Session.retrieve(bill.stripe_deposit_id)
                            if session.payment_status == "paid":
                                await billing.mark_deposit_paid(bill.id)
                                await self._notify_payment(bill, "deposit")
                        except Exception:
                            pass

                    if bill.stripe_final_id and not bill.final_paid:
                        try:
                            session = stripe.checkout.Session.retrieve(bill.stripe_final_id)
                            if session.payment_status == "paid":
                                await billing.mark_final_paid(bill.id)
                                await self._notify_payment(bill, "final")
                        except Exception:
                            pass
        except Exception as e:
            self.bot.logger.error(f"Payment poll error: {e}")

    async def _notify_payment(self, bill, payment_type: str):
        async with self.bot.db.commission_session() as session:
            comm = await session.get_comm(bill.commission_id)
            if comm and comm.ticket_channel_id:
                channel = self.bot.get_channel(comm.ticket_channel_id)
                if channel:
                    await channel.send(
                        embed=Embed(
                            title="Payment Received",
                            description=f"{payment_type.title()} payment confirmed automatically.",
                            colour=Colour.green()
                        )
                    )
```

- [ ] **Step 5: Commit**

```bash
git add modules/BillingSystem.py pyproject.toml uv.lock
git commit -m "feat: add Stripe integration with payment links and polling"
```

---

### Task 9: Final Integration Test

**Files:** None (testing only)

- [ ] **Step 1: Full workflow test**

1. Start bot: `uv run python main.py`
2. Create ticket via existing system
3. Run `/commission create` to create commission
4. Run `/commission assign @yourself`
5. Run `/commission start`
6. Run `/bill create 100 50`
7. Run `/bill status`
8. Run `/bill confirm deposit`
9. Run `/bill confirm final`
10. Run `/commission complete`
11. Run `/commission info` to verify

- [ ] **Step 2: Test config toggles**

1. `/config payments status`
2. `/config payments stripe disable`
3. `/config payments status` (verify changed)
4. `/config payments stripe enable`

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify full commission billing workflow"
```
