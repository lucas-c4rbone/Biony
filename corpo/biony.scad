// Corpo do Biony (totem) — OpenSCAD
// Mesmo projeto do biony.kcl (Zoo), em milímetros.
//
// Como usar: abra no OpenSCAD, escolha a peça em `parte`, aperte F6 (render) e
// depois Arquivo → Exportar → STL. Ajuste as medidas abaixo quando medir as peças reais.
//
// Eixos: X = largura, Y = profundidade (frente em Y=0, fundo em Y=profundidade), Z = altura.

/* [O que mostrar / exportar] */
// montado | explodido | frente | tampa (frente e tampa já saem deitadas, prontas para imprimir)
parte = "explodido"; // [montado, explodido, frente, tampa]

/* [Corpo] */
largura = 74;
altura = 102;
profundidade = 56;
parede = 2.4;
raio_vertical = 6;      // quinas verticais
raio_frente = 4;        // arredondado das bordas de cima/baixo da frente
corte_y = 44;           // onde o corpo se divide em frente + tampa traseira

/* [Tela 2,4"] */
tela_janela = [50, 38]; // abertura que aparece na frente (largura, altura)
tela_raio = 2;
tela_centro_z = 72;
tela_placa_largura = 61.5; // ⚠️ medir a placa real
tela_folga = 0.2;
tela_vao_trilhos = 44;     // altura da placa da tela (vão entre os trilhos)
trilho_comprimento = 50;
trilho_espessura = 1.6;
trilho_profundidade = 6;
batente_altura = 20;

/* [Alto-falante 40 mm] */
falante_centro_z = 24.5;
falante_anel_interno = 40.5;
falante_anel_externo = 44;
falante_anel_profundidade = 4;
grade_furo = 1.6;
grade_passo = 3.2;
grade_area = [36, 16];
grade_raio = 6;
grade_centro_z = 20;

/* [Microfone INMP441] */
mic_furo = 1.2;
mic_y = 30;               // tem que ficar na frente do corte (corte_y)
mic_encaixe = 14.5;
mic_encaixe_profundidade = 1.5;

/* [XIAO ESP32S3] */
xiao_largura = 17.8;
trilho_xiao_largura = 2;
trilho_xiao_altura = 9;   // os pinos soldados ficam pendurados entre os trilhos
trilho_xiao_comprimento = 20.7;
trilho_xiao_folga_fundo = 0.3;

/* [Tampa, parafusos e pés] */
lingueta_profundidade = 3;
lingueta_espessura = 1.2;
lingueta_folga = 0.2;
ressalto_diametro = 6;
ressalto_comprimento = 10;
ressalto_furo = 2.2;      // furo guia para parafuso M2,5
ressalto_x = 5.0;
ressalto_z = 7.4;
parafuso_folga = 2.9;
escareado = 5;
usb = [13, 7.5];
usb_raio = 3;
usb_centro_z = 14;
ventilacao = [30, 2];
ventilacao_quantidade = 5;
ventilacao_passo = 4;
ventilacao_centro_z = 30;
pe_diametro = 8;
pe_profundidade = 1;
pe_recuo = 10;

$fn = 64;
e = 0.01; // sobra para os cortes não deixarem "pele" de 0 mm

// ------------------------------------------------------------------ formas básicas

// Caixa com quinas verticais arredondadas e as bordas de cima/baixo da FRENTE arredondadas.
module caixa(tam, rv, rf) {
    w = tam[0]; d = tam[1]; h = tam[2];
    hull() {
        // traseira: cilindros em pé, borda de trás reta em cima e embaixo
        for (x = [rv, w - rv]) translate([x, d - rv, 0]) cylinder(r = rv, h = h);
        // frente: "rosquinhas" fazem o arredondado vertical e o de cima/baixo ao mesmo tempo
        for (x = [rv, w - rv], z = [rf, h - rf])
            translate([x, rv, z]) rotate_extrude() intersection() {
                translate([rv - rf, 0]) circle(r = rf);
                translate([0, -rf]) square([rv, 2 * rf]);  // só o lado x >= 0 (o hull completa o resto)
            }
    }
}

module retangulo_arredondado(tam, r) {
    offset(r = r) offset(delta = -r) square(tam, center = true);
}

// Corta um furo retangular arredondado atravessando uma parede no plano XZ.
module furo_xz(tam, r, centro_x, centro_z, y0, espessura) {
    translate([centro_x, y0 + espessura, centro_z]) rotate([90, 0, 0])
        linear_extrude(espessura) retangulo_arredondado(tam, r);
}

module externo() { caixa([largura, profundidade, altura], raio_vertical, raio_frente); }

module cavidade() {
    translate([parede, parede, parede])
        caixa([largura - 2 * parede, profundidade - 2 * parede, altura - 2 * parede],
              raio_vertical - parede, max(raio_frente - parede, 0.5));
}

module casca() { difference() { externo(); cavidade(); } }

module metade_frente() { intersection() { children(); translate([-1, -1, -1]) cube([largura + 2, corte_y + 1, altura + 2]); } }
module metade_tras()   { intersection() { children(); translate([-1, corte_y, -1]) cube([largura + 2, profundidade, altura + 2]); } }

cx = largura / 2;

// ------------------------------------------------------------------ peças internas

module trilhos_tela() {
    for (z = [tela_centro_z - tela_vao_trilhos / 2 - trilho_espessura, tela_centro_z + tela_vao_trilhos / 2])
        translate([cx - trilho_comprimento / 2, parede - e, z])
            cube([trilho_comprimento, trilho_profundidade + e, trilho_espessura]);
}

module batentes_tela() {
    interno = cx - tela_placa_largura / 2 - tela_folga; // até onde o batente avança
    for (lado = [0, 1]) {
        x0 = lado == 0 ? parede - e : largura - interno;
        translate([x0, parede - e, tela_centro_z - batente_altura / 2])
            cube([interno - parede + e, trilho_profundidade + e, batente_altura]);
    }
}

module anel_falante() {
    translate([cx, parede - e, falante_centro_z]) rotate([-90, 0, 0])
        difference() {
            cylinder(d = falante_anel_externo, h = falante_anel_profundidade + e);
            translate([0, 0, -e]) cylinder(d = falante_anel_interno, h = falante_anel_profundidade + 3 * e);
        }
}

module trilhos_xiao() {
    fim = profundidade - parede - trilho_xiao_folga_fundo;
    for (x = [cx - xiao_largura / 2 - trilho_xiao_largura, cx + xiao_largura / 2])
        translate([x, fim - trilho_xiao_comprimento, parede - e])
            cube([trilho_xiao_largura, trilho_xiao_comprimento, trilho_xiao_altura + e]);
}

function posicoes_ressaltos() = [for (x = [ressalto_x, largura - ressalto_x], z = [ressalto_z, altura - ressalto_z]) [x, z]];

module ressaltos() {
    for (p = posicoes_ressaltos())
        translate([p[0], corte_y - ressalto_comprimento, p[1]]) rotate([-90, 0, 0])
            difference() {
                cylinder(d = ressalto_diametro, h = ressalto_comprimento);
                translate([0, 0, -e]) cylinder(d = ressalto_furo, h = ressalto_comprimento + 2 * e);
            }
}

// ------------------------------------------------------------------ cortes

// Furos da grade só onde o furo inteiro cabe dentro do retângulo arredondado.
function dentro_grade(x, z) =
    let(w = grade_area[0] / 2 - grade_furo / 2, h = grade_area[1] / 2 - grade_furo / 2, r = max(grade_raio - grade_furo / 2, 0))
    (abs(x) <= w - r && abs(z) <= h) || (abs(x) <= w && abs(z) <= h - r) ||
    norm([abs(x) - (w - r), abs(z) - (h - r)]) <= r;

module grade() {
    nx = floor(grade_area[0] / 2 / grade_passo);
    nz = floor(grade_area[1] / 2 / grade_passo);
    for (i = [-nx:nx], k = [-nz:nz])
        if (dentro_grade(i * grade_passo, k * grade_passo))
            translate([cx + i * grade_passo, parede + e, grade_centro_z + k * grade_passo]) rotate([90, 0, 0])
                cylinder(d = grade_furo, h = parede + 2 * e, $fn = 16);
}

module microfone() {
    translate([cx, mic_y, altura - parede - e]) cylinder(d = mic_furo, h = parede + 2 * e, $fn = 24);
    translate([cx, mic_y, altura - parede - mic_encaixe_profundidade]) cylinder(d = mic_encaixe, h = mic_encaixe_profundidade + e);
}

module pes() {
    for (x = [pe_recuo, largura - pe_recuo], y = [pe_recuo, profundidade - pe_recuo])
        translate([x, y, -e]) cylinder(d = pe_diametro, h = pe_profundidade + e);
}

// ------------------------------------------------------------------ peças

module frente() {
    difference() {
        union() {
            metade_frente() casca();
            trilhos_tela();
            batentes_tela();
            anel_falante();
            trilhos_xiao();
            ressaltos();
        }
        furo_xz(tela_janela, tela_raio, cx, tela_centro_z, -e, parede + 2 * e);
        grade();
        microfone();
        pes();
    }
}

module lingueta() {
    externo_w = largura - 2 * (parede + lingueta_folga);
    externo_h = altura - 2 * (parede + lingueta_folga);
    interno_w = externo_w - 2 * lingueta_espessura;
    interno_h = externo_h - 2 * lingueta_espessura;
    base = 1.5; // dentro da tampa, a lingueta encosta nas paredes para ficar presa a elas
    difference() {
        union() {
            // a parte que entra na frente (com folga)
            translate([cx, corte_y + e, altura / 2]) rotate([90, 0, 0])
                linear_extrude(lingueta_profundidade + e) difference() {
                    square([externo_w, externo_h], center = true);
                    square([interno_w, interno_h], center = true);
                }
            // a base, colada nas paredes da tampa
            translate([cx, corte_y + base, altura / 2]) rotate([90, 0, 0])
                linear_extrude(base + e) difference() {
                    square([largura - 2 * parede + 2 * e, altura - 2 * parede + 2 * e], center = true);
                    square([interno_w, interno_h], center = true);
                }
        }
        // folga para os ressaltos dos parafusos e para os trilhos da XIAO, que atravessam o corte
        for (p = posicoes_ressaltos())
            translate([p[0], corte_y - lingueta_profundidade - 1, p[1]]) rotate([-90, 0, 0])
                cylinder(d = ressalto_diametro + 0.6, h = lingueta_profundidade + 2);
        translate([0, corte_y - lingueta_profundidade - 1, 0]) hull() trilhos_xiao_folga();
    }
}

module trilhos_xiao_folga() {
    for (x = [cx - xiao_largura / 2 - trilho_xiao_largura - 0.3, cx + xiao_largura / 2 + trilho_xiao_largura + 0.3])
        translate([x, 0, 0]) cube([e, lingueta_profundidade + 4, parede + trilho_xiao_altura + 0.3]);
}

module tampa() {
    difference() {
        union() {
            metade_tras() casca();
            lingueta();
        }
        // parafusos M2,5 com escareado por fora
        for (p = posicoes_ressaltos()) {
            translate([p[0], profundidade - parede - e, p[1]]) rotate([-90, 0, 0])
                cylinder(d = parafuso_folga, h = parede + 2 * e);
            translate([p[0], profundidade + e, p[1]]) rotate([90, 0, 0])
                cylinder(d1 = escareado, d2 = parafuso_folga, h = (escareado - parafuso_folga) / 2 + e);
        }
        furo_xz(usb, usb_raio, cx, usb_centro_z, profundidade - parede - e, parede + 2 * e);
        for (i = [0 : ventilacao_quantidade - 1])
            furo_xz(ventilacao, 0.9, cx,
                    ventilacao_centro_z + (i - (ventilacao_quantidade - 1) / 2) * ventilacao_passo,
                    profundidade - parede - e, parede + 2 * e);
        pes();
    }
}

// ------------------------------------------------------------------ cena

if (parte == "montado") {
    frente(); tampa();
} else if (parte == "explodido") {
    color("lightgray") frente();
    color("gray") translate([0, 25, 0]) tampa();
} else if (parte == "frente") {
    // deitada com a FRENTE na mesa: melhor acabamento na tela, na grade e nas bordas
    rotate([90, 0, 0]) frente();
} else if (parte == "tampa") {
    // deitada com o FUNDO (lado de fora) na mesa
    translate([0, 0, profundidade]) rotate([-90, 0, 0]) tampa();
}
