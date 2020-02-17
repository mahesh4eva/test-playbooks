/*
 * Tests to ensure that the application is functioning at a basic level.
 * This suite should have read-only tests. When adding tests to this file,
 * avoiding actually creating/deleting/editing resources.
 */
context('Sanity checks', function() {
  it('Cannot log in with bad credentials and error text is helpful', function() {
    // Every test is preceded by an API login, so for this one we log out first.
    cy.visit('')
    cy.get('#toolbar-user-dropdown').click()
    cy.get('#logout-button').click()
    cy.get('.pf-c-login__container').should('be.visible')

    cy.percySnapshot('Login-page')

    cy.get('#pf-login-username-id').type('BAD_USERNAME')
    cy.get('#pf-login-password-id').type('BAD_PASSWORD')
    cy.get('button[type=submit]').click()

    cy.get('.pf-c-form__helper-text').should('have.text', 'Invalid username or password. Please try again.')

    cy.get('#pf-login-password-id').should('have.attr', 'aria-invalid', 'true')

    cy.percySnapshot('Invalid-Username-Password-Login-Page')

  })

  it('Navigation Bar correctly links to the corresponding page', function() {
    // Navigation bar check
    cy.visit('')

    // Expand all Navbar groups
    cy.get('[data-component="pf-nav-expandable"][aria-expanded="false"]')
      .each(function(item) {
        cy.wrap(item).click()
      })
      .then(function() {
        // Verify that each navbar item links to the correct page
        const navItem = '.pf-c-nav__item'
        const header = '.pf-c-breadcrumb__heading'

        // Not implemented
        //cy.get(`${navItem} > [href="/#/home"]`).click()
        //cy.get(header).should('have.text', 'Dashboard')

        cy.get(`${navItem} > [href="/#/jobs"]`).click()
        cy.get(header).should('have.text', 'Jobs')
        cy.get('[aria-label="Jobs List"]')
        cy.percySnapshot('Jobs-Page')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/schedules"]`).click()
        //cy.get(header).should('have.text', 'Schedules')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/portal"]`).click()
        //cy.get(header).should('have.text', 'My View')

        cy.get(`${navItem} > [href="/#/templates"]`).click()
        cy.get(header).should('have.text', 'Templates')
        cy.get('#template-list-toolbar')
        cy.get('[aria-label="Templates List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Templates-Page')

        cy.get(`${navItem} > [href="/#/credentials"]`).click()
        cy.get(header).should('have.text', 'Credentials')
        cy.get('#credential-list-toolbar')
        cy.get('[aria-label="Items List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Credentials-page')

        cy.get(`${navItem} > [href="/#/projects"]`).click()
        cy.get(header).should('have.text', 'Projects')
        cy.get('#project-list-toolbar')
        cy.get('[aria-label="Projects List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Projects-Page')

        cy.get(`${navItem} > [href="/#/inventories"]`).click()
        cy.get(header).should('have.text', 'Inventories')
        cy.get('#inventory-list-toolbar')
        cy.get('[aria-label="Inventories List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Inventory-Page')

        cy.get(`${navItem} > [href="/#/hosts"]`).click()
        cy.get(header).should('have.text', 'Hosts')
        cy.get('#host-list-toolbar')
        cy.get('[aria-label="Hosts List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Hosts-Page')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/inventory_scripts"]`).click()
        //cy.get(header).should('have.text', 'Inventory Scripts')

        cy.get(`${navItem} > [href="/#/organizations"]`).click()
        cy.get(header).should('have.text', 'Organizations')
        cy.get('#organization-list-toolbar')
        cy.get('[aria-label="Organizations List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Organization-Page')

        cy.get(`${navItem} > [href="/#/users"]`).click()
        cy.get(header).should('have.text', 'Users')
        cy.get('#user-list-toolbar')
        cy.get('[aria-label="Users List"]')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Users-Page')

        cy.get(`${navItem} > [href="/#/teams"]`).click()
        cy.get(header).should('have.text', 'Teams')
        cy.get('#team-list-toolbar')
        cy.get('[aria-label="Add"]')
        cy.percySnapshot('Teams-Page')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/credential_types"]`).click()
        //cy.get(header).should('have.text', 'Credential Types')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/notification_templates"]`).click()
        //cy.get(header).should('have.text', 'Notification Templates')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/management_jobs"]`).click()
        //cy.get(header).should('have.text', 'Management Jobs')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/instance_groups"]`).click()
        //cy.get(header).should('have.text', 'Instance Groups')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/applications"]`).click()
        //cy.get(header).should('have.text', 'Applications')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/auth_settings"]`).click()
        //cy.get(header).should('have.text', 'Authentication Settings')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/jobs_settings"]`).click()
        //cy.get(header).should('have.text', 'Jobs Settings')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/system_settings"]`).click()
        //cy.get(header).should('have.text', 'System Settings')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/ui_settings"]`).click()
        //cy.get(header).should('have.text', 'User Interface Settings')

        // Not implemented
        //cy.get(`${navItem} > [href="/#/license"]`).click()
        //cy.get(header).should('have.text', 'License')

      })
  })

  it ('Can close modal with Cancel and X buttons', function() {
    //The following is an easy way to get to a modal without any data
    cy.visit('/#/organizations/add')
    cy.get('#org-instance-groups').click()
    cy.percySnapshot('Modal-1')
    cy.get('[aria-label="Close"]').click()
    cy.percySnapshot('After-Modal-Close')

    cy.get('#org-instance-groups').click()
    cy.percySnapshot('Modal-2')
    cy.get('.pf-c-modal-box__footer > .pf-m-secondary').click()
    cy.get('#org-instance-groups').should('be.visible')
    cy.percySnapshot('After-Modal-Close-with-X-button')

  })

  it ('Navbar can be opened and closed', function () {
    cy.visit('')
    cy.get('#page-sidebar').should('be.visible')
    cy.percySnapshot('NavBar-visible-1')
    cy.get('#nav-toggle').click()
    cy.get('#page-sidebar').should('not.be.visible')
    cy.percySnapshot('NavBar-not-visible')
    cy.get('#nav-toggle').click()
    cy.get('#page-sidebar').should('be.visible')
    cy.percySnapshot('NavBar-visible-2')
  })



})
