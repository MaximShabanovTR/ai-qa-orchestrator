from dataclasses import dataclass
from models.requirement import StructuredRequirement, TestScope as Scope


@dataclass
class EvalFixture:
    name: str
    requirement: StructuredRequirement


# --- curated dataset ---
# Requirements are pre-built to isolate TestCaseGenerator quality from
# RequirementsAnalyst variance. Each fixture is deliberately chosen to
# stress a different aspect of the generator:
#   password_reset  — straightforward linear flow, clear ACs
#   shopping_cart   — stateful operations, multiple actors
#   user_profile    — mixed update rules (immediate vs. deferred)

PASSWORD_RESET = EvalFixture(
    name="password_reset",
    requirement=StructuredRequirement(
        title="Password Reset",
        description=(
            "Registered users can reset a forgotten password by requesting "
            "an email with a unique, single-use reset link. "
            "The link expires after 24 hours."
        ),
        actors=["Registered user", "Email service"],
        acceptance_criteria=[
            "User receives a reset email after submitting their address",
            "Reset link is single-use and cannot be reused after activation",
            "Reset link expires after 24 hours",
            "User can set a new password via the link",
            "User is redirected to the login page after a successful reset",
        ],
        test_scope=Scope(
            in_scope=["reset request", "email delivery", "link expiry", "password update"],
            out_of_scope=["login flow", "registration", "account lockout"],
        ),
        raw_input=(
            "Registered users can reset a forgotten password by requesting "
            "an email with a unique, single-use reset link. "
            "The link expires after 24 hours."
        ),
    ),
)

SHOPPING_CART = EvalFixture(
    name="shopping_cart",
    requirement=StructuredRequirement(
        title="Shopping Cart Management",
        description=(
            "Authenticated users can add products to a cart, update quantities, "
            "and remove items. The cart persists across sessions and displays "
            "the running total including applicable taxes."
        ),
        actors=["Authenticated user", "Product catalog", "Tax service"],
        acceptance_criteria=[
            "User can add a product to the cart",
            "User can change the quantity of a cart item",
            "User can remove an item from the cart",
            "Cart persists when the user logs out and back in",
            "Cart displays the correct total price including tax",
        ],
        test_scope=Scope(
            in_scope=["add to cart", "quantity update", "item removal", "cart persistence", "price calculation"],
            out_of_scope=["checkout", "payment", "order history"],
        ),
        raw_input=(
            "Authenticated users can add products to a cart, update quantities, "
            "and remove items. The cart persists across sessions."
        ),
    ),
)

USER_PROFILE = EvalFixture(
    name="user_profile",
    requirement=StructuredRequirement(
        title="User Profile Update",
        description=(
            "Authenticated users can update their display name and avatar immediately. "
            "Email changes require a verification step before taking effect."
        ),
        actors=["Authenticated user", "Email service"],
        acceptance_criteria=[
            "User can update their display name and see the change immediately",
            "User can upload or replace their avatar",
            "Changing email triggers a verification email to the new address",
            "Email change only takes effect after the user clicks the verification link",
            "Unverified email changes do not affect the current login email",
        ],
        test_scope=Scope(
            in_scope=["display name update", "avatar upload", "email change", "email verification"],
            out_of_scope=["password change", "account deletion", "notification preferences"],
        ),
        raw_input=(
            "Authenticated users can update their display name and avatar immediately. "
            "Email changes require a verification step before taking effect."
        ),
    ),
)

ALL_FIXTURES = [PASSWORD_RESET, SHOPPING_CART, USER_PROFILE]
