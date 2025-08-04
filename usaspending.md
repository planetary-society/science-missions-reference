USASpending Python Client – API Reference

(version 0.1.0)

This document describes the public interface of the usaspending Python package, a high‑level wrapper around the USAspending.gov v2 REST API.
It is formatted so that a Large‑Language‑Model (LLM) can reliably parse section boundaries, symbol names, parameters, and type information.

⸻

Contents
	1.	Installation
	2.	Configuration
	3.	Quick‑start
	4.	Top‑level Client
	5.	Resources
	6.	Query‑builder Classes
	7.	Data Models
	8.	Utilities & Helpers
	9.	Exceptions
	10.	Mock Client for Testing

⸻

Configuration

Global settings live in the singleton usaspending.config.config object.
Call config.configure(**kwargs) once at program start; values propagate library‑wide.

Key	Type	Default	Purpose
base_url	str	"https://api.usaspending.gov/api/v2"	API root
user_agent	str	"usaspendingapi-python/0.1.0"	Sent with every request
timeout	int	30 s	Per‑request timeout
max_retries	int	3	Automatic HTTP retry count
retry_delay	float	1.0 s	Base delay before first retry
retry_backoff	float	2.0	Exponential back‑off factor
rate_limit_calls	int	30	Client‑side call limit per rate_limit_period
rate_limit_period	int	1 s	Sliding‑window length
cache_enabled	bool	True	Toggle transparent response caching
cache_backend	{"file","memory"}	"pickle"	cachier backend
cache_dir	str	".usaspending_cache"	On‑disk cache location
cache_ttl	timedelta	7 days	Cache expiry
logging_level	{"DEBUG","INFO",…}	"DEBUG"	Root logging threshold
debug_mode	bool	True	Emit verbose debug logs
log_file	`str 	 None`	None

Example

from usaspending.config import config
config.configure(
    timeout=10,
    rate_limit_calls=20,
    cache_enabled=False,
    logging_level="INFO",
)


⸻

Quick‑start

from usaspending import USASpending
from usaspending.models import Location

client = USASpending()                       # uses global config
awards = (
    client.awards.search()                   # AwardsSearch builder
          .contracts()                      # convenience filter
          .with_keywords("Lunar Lander")
          .for_fiscal_year(2025)
          .limit(100)
)

for award in awards:                         # iteration executes the request(s)
    print(award.generated_id, award.recipient.name, f"${award.award_amount:,.0f}")


⸻

Top‑level Client

class USASpending(base_url: str | None = None, session: requests.Session | None = None)

The root object that orchestrates HTTP, rate‑limiting, retries, and caching.

Property	Type	Description
awards	AwardResource	Award search & lookup
recipients	RecipientsResource	Recipient lookup & spend aggregation
transactions	TransactionsResource	Transaction search for a given award
spending	SpendingResource	“Spending by …” endpoints
funding	FundingResource	Federal‑account funding by award

All resource objects are lazily created and cached per client instance.

⸻

Resources

 class AwardResource

Method	Returns	Notes
get(award_id: str)	`Award 	 None`
search()	AwardsSearch	Starts a chainable query


⸻

 class RecipientsResource

Method	Returns
get(recipient_id: str)	Recipient
search()	SpendingByRecipientsSearch


⸻

 class TransactionsResource

Method	Returns	Example
for_award(award_id: str)	TransactionsSearch	client.transactions.for_award("CONT_AWD_123").limit(50)


⸻

 class FundingResource

Method	Returns	Example
for_award(award_id: str)	FundingSearch	client.funding.for_award("CONT_AWD_123").order_by("fiscal_date")


⸻

 class SpendingResource

Method	Returns	Example
search()	SpendingSearch	Supports .by_recipient() or .by_district() then normal filters


⸻

Query‑builder Classes

All builders share a common fluent interface: every mutator returns a new immutable instance (safe to re‑use baselines). Pagination is transparent; iteration, list(), or .count() execute the request(s).

Common control methods

Method	Description
.limit(n:int)	Stop after n total records
.page_size(n:int)	Override API page length
.max_pages(n:int)	Hard cap on pages fetched
.all()	Materialise to list
.first()	Return first record or None
.count()	Fast tally without fetching all pages

Shared filter helpers (subset)

Helper	Purpose
.with_keywords(*kw)	Full‑text match
.in_time_period(start, end, …, date_type=None)	Date range filter
.for_fiscal_year(year)	Convenience wrapper
.for_agency(name, agency_type="awarding", tier="toptier")	Agency filter
.with_award_types(*codes)	Contract/Grant/… type codes
.with_recipient_id(id) / .with_recipient_search_text("UEI…")	Recipient filters

Builder matrix

Builder	Origin property	Special helpers
AwardsSearch	client.awards.search()	.contracts() .grants() .idvs() .loans() convenience; additional numeric & NAICS/PSC/TAS filters
TransactionsSearch	client.transactions.for_award()	.since("YYYY‑MM‑DD") .until("YYYY‑MM‑DD") (client‑side date filter)
FundingSearch	client.funding.for_award()	.order_by(field, dir="desc") supports friendly names ("fiscal_date", "obligation", …)
SpendingSearch	client.spending.search()	.by_recipient() / .by_district(); .spending_level("awards" | "transactions" | "subawards")
SpendingByRecipientsSearch	client.recipients.search()	identical filters to SpendingSearch but category pre‑filled

All filters are implemented as lightweight data classes in usaspending.queries.filters.

⸻

Data Models

Every record returned by a query is mapped to a rich Python object:

Class	Represents	Key Properties (selection)
Award (base)	Generic award	generated_id, recipient, period_of_performance, award_amount
Contract, Grant, Loan, IDV, DirectPayment, OtherAssistance	Typed award subclasses	Add type‑specific fields (product_or_service_code, loan_value, …)
Transaction	Single obligation action	action_date, federal_action_obligation, description
Recipient	UEI/DUNS entity	name, business_types, location
Funding	Federal Account line item	reporting_fiscal_year, gross_outlay_amount
Spending	Aggregated spend row	category‑dependent attributes
Location, PeriodOfPerformance, etc.	value objects	

All models inherit from BaseModel (dict‑like .raw() accessor) and many are lazy‑loading subclasses of LazyRecord – accessing a missing attribute triggers a follow‑up API call transparently.

⸻

Utilities & Helpers
	•	utils.RateLimiter – thread‑safe sliding‑window limiter; used by the client.
	•	utils.RetryHandler – jittered exponential back‑off wrapper around requests.
	•	utils.formatter – NASA‑centric text‑cleaning helpers (contracts_titlecase, etc.).

⸻

Exceptions

All custom errors derive from USASpendingError.

Exception	Raised when…
APIError(status_code, response_body)	API returns HTTP 4xx/5xx
HTTPError(status_code)	Unexpected transport failure
RateLimitError    Rate limit exceeded
ValidationError	Client‑side parameter validation fails
ConfigurationError	Invalid config.configure() argument


⸻

Mock Client for Testing

tests.mocks.MockUSASpendingClient provides drop‑in replacements for unit tests:

from tests.mocks import MockUSASpendingClient

client = MockUSASpendingClient()
client.mock_award_search([{"Award ID": "1"}, {"Award ID": "2"}])
assert len(list(client.awards.search().contracts())) == 2

Features include automatic pagination, fixture loaders, error simulation, and call‑count assertions.

⸻

License

See the repository’s LICENSE file (not included in this reference).