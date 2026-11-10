let fixture;
let previews;
const display = email => cy.document().then(doc => {
    const parsed = new doc.defaultView.DOMParser().parseFromString(email.html, 'text/html');
    doc.head.innerHTML = parsed.head.innerHTML;
    doc.body.innerHTML = parsed.body.innerHTML;
    doc.body.setAttribute('style', parsed.body.getAttribute('style') || '');
});

describe('Workflow email presentation after mailbox acceptance', () => {
    before(() => {
        cy.task('emailLayoutSeed').then(result => { fixture = result; });
        cy.task('emailLayoutPreviews').then(result => { previews = result; });
    });
    beforeEach(() => {
        cy.login(fixture.editor, fixture.password);
        cy.visit('/app');
    });
    after(() => cy.task('emailLayoutCleanup'));

    it('uses recipient-language subjects and business document labels in all seven families', () => {
        expect(previews).to.have.length(21);
        for (const email of previews) {
            expect(email.subject).not.to.match(/WFMAIL|position-\d|PRJ-2026|User Timesheet Position/);
            const ru = email.language !== 'en';
            expect(email.subject.toLowerCase()).to.include(ru
                ? (email.name.includes('Correction') ? 'исправление' : email.name.includes('Deadline') ? 'срок' : 'согласован')
                : (email.name.includes('Correction') ? 'Correction' : email.name.includes('Deadline') ? 'deadline' : 'Approval').toLowerCase());
            display(email);
            cy.get('h1').should('be.visible');
            cy.get('body').invoke('text').should('not.match', /WFMAIL|position-\d|PRJ-2026/);
            cy.get('[data-dinext-email-footer="1"] img[alt="Dinext"]').should('have.length', 1);
        }
    });

    it('keeps compact headers and padded separated buttons on mobile even without anchor spacing', () => {
        for (const email of previews) {
            for (const width of [1024, 360, 390, 430]) {
                cy.viewport(width, 1100);
                display(email);
                cy.document().should(doc => {
                    expect(doc.documentElement.scrollWidth).to.be.at.most(width);
                    const heading = doc.querySelector('h1');
                    const header = heading.closest('td');
                    expect(header.querySelectorAll('img')).to.have.length(0);
                    expect(header.getBoundingClientRect().height).to.be.at.most(128);
                    expect(header.getBoundingClientRect().top).to.be.at.most(24);
                    for (const a of doc.querySelectorAll('a[href*="preview_action"]')) {
                        a.style.removeProperty('padding');
                        a.style.removeProperty('margin');
                        const td = a.closest('td');
                        const style = doc.defaultView.getComputedStyle(td);
                        expect(parseFloat(style.paddingTop)).to.be.at.least(8);
                        expect(parseFloat(style.paddingLeft)).to.be.at.least(10);
                        expect(td.querySelectorAll('a[href*="preview_action"]')).to.have.length(1);
                    }
                    // Outlook may discard display:inline-table. The table row is the layout.
                    for (const table of doc.querySelectorAll('table')) table.style.removeProperty('display');
                    const groups = new Map();
                    for (const a of doc.querySelectorAll('a[href*="preview_action"]')) {
                        const row = a.closest('table').parentElement.closest('tr');
                        if (!groups.has(row)) groups.set(row, []);
                        groups.get(row).push(a);
                    }
                    for (const links of groups.values()) {
                        expect(links).to.have.length(2);
                        const first = links[0].getBoundingClientRect();
                        const second = links[1].getBoundingClientRect();
                        expect(Math.abs(first.top-second.top)).to.be.at.most(2);
                        expect(second.left-first.right).to.be.at.least(6);
                    }
                });
                if (email.language === 'ru' && [1024, 390].includes(width)) {
                    for (const theme of ['light', 'dark']) {
                        cy.document().then(doc => { doc.body.style.backgroundColor = theme === 'dark' ? '#242424' : '#ffffff'; const footer = doc.querySelector('.email-footer-container'); expect(doc.defaultView.getComputedStyle(footer).backgroundColor).to.equal('rgb(243, 245, 248)'); });
                        cy.screenshot(email.name.replaceAll(' ', '-') + '-' + width + '-' + theme);
                    }
                    if (width === 390) {
                        cy.get('img').invoke('removeAttr', 'src');
                        cy.screenshot(email.name.replaceAll(' ', '-') + '-390-images-off');
                    }
                }
            }
        }
    });

    it('extends the footer background to the full message width with aligned contents', () => {
        for (const email of previews) {
            for (const width of [360, 390, 1024]) {
                cy.viewport(width, 1000);
                display(email);
                cy.document().should(doc => {
                    const footer = doc.querySelector('table[bgcolor="#f3f5f8"]');
                    const background = doc.querySelector('h1').closest('table').parentElement.closest('table');
                    const actual = footer.getBoundingClientRect();
                    const expected = background.getBoundingClientRect();
                    expect(Math.abs(actual.left-expected.left)).to.be.at.most(1);
                    expect(Math.abs(actual.width-expected.width)).to.be.at.most(1);
                    const logo = doc.querySelector('[data-dinext-email-footer="1"] img');
                    const heading = doc.querySelector('h1');
                    expect(Math.abs(logo.getBoundingClientRect().left-heading.getBoundingClientRect().left)).to.be.at.most(3);
                });
            }
        }
    });

    it('shows one project rejection for the two-role decision', () => {
        display(previews.find(p => p.name === 'Dinext Workflow Digest' && p.language === 'ru'));
        cy.get('a[href*="preview_action"]').should('have.length', 2);
        cy.get('body').invoke('text').should(text => expect((text.match(/Не согласовано/g) || [])).to.have.length(1));
    });

    it('shows localized recorded hour comments after each timesheet position total', () => {
        for (const language of ['ru', 'en', 'system']) {
            display(previews.find(p => p.name === 'Dinext Timesheet Workflow Digest' && p.language === language));
            const text = language === 'en'
                ? 'Hours: 8 (2 h — testing, 3.5 h — development, 2.5 h — documentation)'
                : 'Часы: 8 (2 ч. — тестирование, 3,5 ч. — доработка, 2,5 ч. — документация)';
            cy.get('p').filter((_, p) => p.textContent === text).should('have.length', 2);
        }
    });

    it('shows parent timesheets and responsible approvers without positions or author sections in overdue mail', () => {
        const email = previews.find(p => p.name === 'Dinext Timesheet Workflow Deadline Digest' && p.language === 'ru');
        display(email);
        cy.get('a[href$="/november-week-45"]').should('have.length', 1);
        cy.get('body').invoke('text').should('include', 'Мария Соколова').and('include', 'Алексей Смирнов')
            .and('include', 'Самый ранний нарушенный срок').and('include', 'Часы просрочки')
            .and('not.include', '№ 2').and('not.include', 'Архитектор решения');
        cy.get('h2, a[href*="preview_action"]').should('not.exist');
        cy.document().should(doc => {
            const color = doc.defaultView.getComputedStyle(doc.querySelector('h1').closest('td')).backgroundColor;
            const rgb = color.match(/\d+/g).map(Number);
            expect(rgb[0] - rgb[2]).to.be.at.least(40);
        });
    });
});
