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
