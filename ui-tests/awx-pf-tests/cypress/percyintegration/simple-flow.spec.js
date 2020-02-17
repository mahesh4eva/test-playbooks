/*
 * Tests to perform visual regression on basic flow for all resources
 * This contains modals, details page, edit page and lookup
 */
context('Inventory', function() {
beforeEach(function() {
      cy.wrap(arr5).each(function(i) {
        cy.akit(`inventory.get_or_create(name="test-inventory-${i}")`).as(`inventory${i}`)
      })
      })
  let arr5 = Array.from({ length: 5 }, (v, k) => k + 1) // Small array
  it('all buttons on templates page work properly, and the elements are displayed correctly', function() {
    const navItem = '.pf-c-nav__item'
    const header = '.pf-c-breadcrumb__heading'
    cy.visit('')
    cy.get('[data-component="pf-nav-expandable"][aria-expanded="false"]').within(() => {
      cy.contains('Resources').click()
    })
    cy.get(`${navItem} > [href="/#/inventories"]`).click()
    cy.get(header).should('have.text', 'Inventories')
    cy.get('[aria-label="Inventories List"]')
    cy.get('[aria-label="Add"]')
    cy.get('input[type=search]').type('test-inventory-')
    cy.get('[aria-label="Search submit button"]').click()
    cy.get('[aria-label="Inventories List"]')
      .find('li')
      .should('have.length', 5)
    cy.percySnapshot('Inventories-Page')
    cy.get(`input[id="select-inventory-${this.inventory1.id}"][type="checkbox"]:enabled`).click()
    cy.get('button[aria-label="Delete"]:enabled').click()
    cy.wait(2000)
    cy.percySnapshot('Inventories-Page-Delete-Modal')
    cy.get('button[aria-label="cancel delete"]:enabled').click()
    cy.get(`a[href="#/inventories/inventory/${this.inventory1.id}/details"]`).click()
    cy.wait(2000)
    cy.percySnapshot('Inventories-Page-Details-Page')
    cy.get('a[href*="/edit"]').click()
     cy.wait(5000)
    cy.percySnapshot('Inventories-Page-Edit-Page')
    cy.get('#organization').click()
    cy.wait(3000)
    cy.percySnapshot('Inventories-Page-Lookup')
    cy.get('.pf-c-modal-box__footer .pf-m-secondary').click()
  })
})

context('Project', function() {
beforeEach(function() {
      cy.wrap(arr5).each(function(i) {
        cy.akit(`projects.get_or_create(name="test-project-${i}")`).as(`project${i}`)
      })
      })
  let arr5 = Array.from({ length: 5 }, (v, k) => k + 1) // Small array
  it('all buttons on templates page work properly, and the elements are displayed correctly', function() {
    const navItem = '.pf-c-nav__item'
    const header = '.pf-c-breadcrumb__heading'
    cy.visit('')
    cy.get('[data-component="pf-nav-expandable"][aria-expanded="false"]').within(() => {
      cy.contains('Resources').click()
    })
    cy.get(`${navItem} > [href="/#/projects"]`).click()
    cy.get(header).should('have.text', 'Projects')
    cy.get('[aria-label="Projects List"]')
    cy.get('[aria-label="Add"]')
    cy.get('input[type=search]').type('test-project-')
    cy.get('[aria-label="Search submit button"]').click()
    cy.get('[aria-label="Projects List"]')
      .find('li')
      .should('have.length', 5)
    cy.percySnapshot('Projects-Page')
    cy.get(`input[id="select-project-${this.project1.id}"][type="checkbox"]:enabled`).click()
    cy.get('button[aria-label="Delete"]:enabled').click()
    cy.wait(2000)
    cy.percySnapshot('Projects-Page-Delete-Modal')
    cy.get('button[aria-label="cancel delete"]:enabled').click()
    cy.get(`a[href="#/projects/${this.project1.id}"]`).click()
    cy.wait(2000)
    cy.percySnapshot('Projects-Page-Details-Page')
    cy.get('a[href*="/edit"]').click()
     cy.wait(5000)
    cy.percySnapshot('Projects-Page-Edit-Page')
    cy.get('#organization').click()
    cy.wait(3000)
    cy.percySnapshot('Projects-Page-Lookup')
    cy.get('.pf-c-modal-box__footer .pf-m-secondary').click()
      })
  })


context('Templates', function() {
beforeEach(function() {
      cy.wrap(arr5).each(function(i) {
        cy.akit(`job_templates.get_or_create(name="test-template-${i}")`).as(`template${i}`)
      })
      })
  let arr5 = Array.from({ length: 5 }, (v, k) => k + 1) // Small array
  it('all buttons on templates page work properly, and the elements are displayed correctly', function() {
    const navItem = '.pf-c-nav__item'
    const header = '.pf-c-breadcrumb__heading'
    cy.visit('')
    cy.get('[data-component="pf-nav-expandable"][aria-expanded="false"]').within(() => {
      cy.contains('Resources').click()
    })
    cy.get(`${navItem} > [href="/#/templates"]`).click()
    cy.get(header).should('have.text', 'Templates')
    cy.get('#template-list-toolbar')
    cy.get('[aria-label="Templates List"]')
    cy.get('[aria-label="Add"]')
    cy.get('input[type=search]').type('test-template-')
    cy.get('[aria-label="Search submit button"]').click()
    cy.get('[aria-label="Templates List"]')
      .find('li')
      .should('have.length', 5)
    cy.percySnapshot('Templates-Page')
    cy.get(`input[id="select-jobTemplate-${this.template1.id}"][type="checkbox"]:enabled`).click()
    cy.get('button[aria-label="Delete"]:enabled').click()
    cy.wait(2000)
    cy.percySnapshot('Templates-Page-Delete-Modal')
    cy.get('button[aria-label="cancel delete"]:enabled').click()
    cy.get(`a[href="#/templates/job_template/${this.template1.id}"]`).click()
    cy.wait(2000)
    cy.percySnapshot('Templates-Page-Details-Page')
    cy.get('[aria-label="close"]').click()
    cy.wait(2000)
    cy.percySnapshot('Templates-Page-label-chip-expand')
    cy.get('[aria-label="close"]').click()
    cy.wait(2000)
    cy.percySnapshot('Templates-Page-label-chip-collapse')
    cy.get('a[aria-label=Edit]').click()
     cy.wait(5000)
    cy.percySnapshot('Templates-Page-Edit-Page')
    cy.get('#inventory-lookup').click()
    cy.wait(3000)
    cy.percySnapshot('Templates-Page-Lookup')
    cy.get('.pf-c-modal-box__footer .pf-m-secondary').click()
      })
  })

context('Credentials', function() {
beforeEach(function() {
        cy.akit(`credentials.get_or_create(name="test-credential-percy-crud")`).as(`cred`)
      })
  it('all buttons on templates page work properly, and the elements are displayed correctly', function() {
    const navItem = '.pf-c-nav__item'
    const header = '.pf-c-breadcrumb__heading'
    cy.visit('')
    cy.get('[data-component="pf-nav-expandable"][aria-expanded="false"]').within(() => {
      cy.contains('Resources').click()
    })
    cy.get(`${navItem} > [href="/#/credentials"]`).click()
    cy.get(header).should('have.text', 'Credentials')
    cy.get('[aria-label="Items List"]')
    cy.get('[aria-label="Add"]')
    cy.get('input[type=search]').type('test-credential-percy-crud')
    cy.get('[aria-label="Search submit button"]').click()
    cy.get('[aria-label="Items List"]')
      .find('li')
      .should('have.length', 1)
    cy.percySnapshot('Credentials-Page')
    cy.get(`input[id="select-credential-${this.cred.id}"][type="checkbox"]:enabled`).click()
    cy.get('button[aria-label="Delete"]:enabled').click()
    cy.wait(2000)
    cy.percySnapshot('Credentials-Page-Delete-Modal')
    cy.get('button[aria-label="cancel delete"]:enabled').click()
    cy.get(`a[href="#/credentials/${this.cred.id}/details"]`).click()
    cy.wait(2000)
    cy.percySnapshot('Credentials-Page-Details-Page')
      })
  })
