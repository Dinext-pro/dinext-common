// The public welcome journey runs as a guest and needs no authentication helpers.
import "./commands";

Cypress.on("uncaught:exception", () => false);
