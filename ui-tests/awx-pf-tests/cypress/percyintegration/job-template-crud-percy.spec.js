context('Can View the Templates page properly', function() {
  it('take snapshot of the Templates page', function() {
    cy.visit('/#/templates')
    cy.get('button[aria-label=Add]')
    cy.percySnapshot()
  })
})
